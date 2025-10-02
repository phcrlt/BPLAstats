# flight_data_processor.py

import pandas as pd
import re
import time
import json
import logging
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
import sys
import os
import glob
import geopandas as gpd
from shapely.geometry import Point
from metrics_calculator import calculate_metrics

from config import DB_URL, UPLOADS_FOLDER

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# === 🗃 СТРУКТУРА ТАБЛИЦЫ ===
DESIRED_COLUMNS = {
    "id": "SERIAL PRIMARY KEY",
    "flight_id": "TEXT",
    "dof": "DATE",
    "opr": "TEXT",
    "reg": "TEXT",
    "typ": "TEXT",
    "typ_desc": "TEXT",
    "sid": "TEXT",
    "source_file": "TEXT",
    "takeoff_time": "TEXT",
    "landing_time": "TEXT",
    "takeoff_coords": "TEXT",
    "landing_coords": "TEXT",
    "takeoff_region_id": "INTEGER",
    "flight_duration_minutes": "INTEGER",
    "created_at": "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
}

TABLE_NAME = "flights"
REGIONS_TABLE = "russia_regions"

# === 📚 РАСШИФРОВКА ТИПОВ ===
TYP_DESCRIPTIONS = {
    "BLA": "беспилотный летательный аппарат",
    "AER": "пилотируемый аэростат",
    "SHAR": "шар-зонд (привязной аэростат, параплан и т.д.)"
}

def find_geojson_file():
    """Находит GeoJSON файл в папке uploads"""
    try:
        # Создаем папку uploads если её нет
        os.makedirs(UPLOADS_FOLDER, exist_ok=True)
        
        # Путь к стандартному файлу
        default_geojson = os.path.join(UPLOADS_FOLDER, "russia_regions.geojson")
        
        if os.path.exists(default_geojson):
            logger.info(f"✅ Найден GeoJSON файл: {default_geojson}")
            return default_geojson
        
        # Если стандартного файла нет, ищем любой .geojson файл
        geojson_files = glob.glob(os.path.join(UPLOADS_FOLDER, "*.geojson"))
        
        if geojson_files:
            # Берем первый найденный файл
            geojson_file = geojson_files[0]
            logger.info(f"✅ Найден GeoJSON файл: {geojson_file}")
            return geojson_file
        else:
            logger.error(f"❌ В папке {UPLOADS_FOLDER} не найдено GeoJSON файлов")
            return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка поиска GeoJSON файла: {e}")
        return None

# === 🔧 ФУНКЦИИ ПАРСИНГА ===

def is_valid_coords(coord_str):
    """Проверяет корректность формата координат (11 или 15 символов)"""
    if not coord_str or pd.isna(coord_str):
        return False
    
    coord_str = str(coord_str).strip().replace(" ", "").upper()
    
    # Проверяем длину
    if len(coord_str) not in [11, 15]:
        return False
    
    # Проверяем наличие направлений N/S и E/W
    has_ns = 'N' in coord_str or 'S' in coord_str
    has_ew = 'E' in coord_str or 'W' in coord_str
    
    if not (has_ns and has_ew):
        return False
    
    # Проверяем, что цифры находятся в правильных позициях
    try:
        if len(coord_str) == 11:
            # Формат DDMMNDDDMME
            int(coord_str[0:4])
            if coord_str[4] not in ['N', 'S']:
                return False
            int(coord_str[5:9])
            if coord_str[10] not in ['E', 'W']:
                return False
        else:  # 15 символов
            # Формат DDMMSSNDDDMMSSE
            int(coord_str[0:6])
            if coord_str[6] not in ['N', 'S']:
                return False
            int(coord_str[7:13])
            if coord_str[14] not in ['E', 'W']:
                return False
    except (ValueError, IndexError):
        return False
    
    return True

def get_best_coords(*coord_sources):
    """Возвращает первые корректные координаты из переданных источников"""
    for coords in coord_sources:
        if is_valid_coords(coords):
            return coords
    return None

def shr_pars(message):
    """Парсинг SHR сообщений"""
    shr = {}
    if not message or len(str(message).strip()) == 0:
        return shr
    try:
        text = str(message).strip()
        
        # Извлекаем flight_id из первой строки (SHR-XXXXX)
        if text.startswith("(SHR-"):
            flight_part = text[5:].split('\n', 1)[0].split()[0]
            shr["flight_id"] = flight_part[:5]
        else:
            shr["flight_id"] = ""

        # Разбиваем на строки и убираем первую строку (SHR-...)
        lines = text.splitlines()
        content_lines = []
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith('-'):
                content_lines.append(stripped[1:].strip())
            elif content_lines:
                content_lines[-1] += " " + stripped

        # Разделяем служебные строки и блок тегов
        service_lines = []
        tag_block_parts = []
        in_tag_block = False

        for line in content_lines:
            if not line:
                continue
            if (line.startswith("ZZZZ") and len(line) <= 12) or \
               (line.startswith("M") and ("/" in line or line[1:5].isdigit())) or \
               (line.startswith("K") and line[1:4].isdigit()):
                if not in_tag_block:
                    service_lines.append(line)
                else:
                    tag_block_parts.append(line)
            else:
                in_tag_block = True
                tag_block_parts.append(line)

        # Обрабатываем служебные строки
        shr["start"] = service_lines[0][:8] if len(service_lines) > 0 else ""
        shr["higth"] = service_lines[1].split()[0] if len(service_lines) > 1 else ""
        shr["end"] = service_lines[2][:8] if len(service_lines) > 2 else ""

        # Собираем основной блок тегов
        main_block = " ".join(tag_block_parts)
        main_block = re.sub(r'\)\s*$', '', main_block).strip()

        # Извлекаем теги с проверкой координат
        tags = ["DEP", "DEST", "DOF", "OPR", "REG", "TYP", "STS", "EET", "RMK", "SID"]
        for tag in tags:
            pattern = rf"{tag}/(.*?)(?=\s+[A-Z]{{3,}}/|$)"
            match = re.search(pattern, main_block, re.DOTALL)
            if match:
                value = match.group(1).strip()
                value = re.sub(r'\)\s*$', '', value)
                
                # Проверяем координаты на корректность
                if tag in ["DEP", "DEST"] and value:
                    if not is_valid_coords(value):
                        shr[f"{tag}_invalid"] = value
                        value = None
                
                shr[tag] = value if value else None
            else:
                shr[tag] = None

        # Проверяем координаты из служебных строк
        for service_line in service_lines:
            if is_valid_coords(service_line):
                shr["service_line_coords"] = service_line

    except Exception as e:
        shr["error"] = f"Ошибка парсинга SHR: {str(e)}"
    return shr

def dep_arr_pars(message):
    """Парсинг DEP/ARR сообщений"""
    res = {}
    if not message or len(str(message).strip()) == 0:
        return res
    try:
        lines = str(message).strip().splitlines()
        for line in lines:
            line = line.strip()
            if not line.startswith('-'):
                continue
            parts = line[1:].split(maxsplit=1)
            if len(parts) < 1:
                continue
            tag = parts[0]
            value = parts[1] if len(parts) > 1 else ""
            
            # Проверяем координаты на корректность для ADEPZ и ADARRZ
            if tag in ["ADEPZ", "ADARRZ"] and value:
                if not is_valid_coords(value):
                    res[f"{tag}_invalid"] = value
                    value = None
            
            res[tag] = value.strip()
    except Exception as e:
        res["error"] = f"Ошибка парсинга: {str(e)}"
    return res

# === 🗄 ФУНКЦИИ РАБОТЫ С БД ===

class RegionFinder:
    """Класс для поиска регионов по координатам используя GeoJSON"""
    
    def __init__(self):
        self.geojson_file = find_geojson_file()
        self.gdf = None
        self.regions_map = {}
        
    def load_regions(self):
        """Загружает регионы из GeoJSON файла"""
        if not self.geojson_file:
            logger.error("❌ GeoJSON файл не найден")
            return False
        
        try:
            self.gdf = gpd.read_file(self.geojson_file)
            logger.info(f"✅ Загружено {len(self.gdf)} регионов из GeoJSON: {os.path.basename(self.geojson_file)}")
            
            # Создаем кэш для быстрого поиска
            for idx, row in self.gdf.iterrows():
                region_id = idx + 1
                self.regions_map[region_id] = {
                    'name': row['region'],
                    'geometry': row['geometry']
                }
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки GeoJSON: {e}")
            return False
    
    def parse_compact_coords_to_decimal(self, coords_str):
        """Парсит компактные координаты формата 554531N0382513E или 5957N02905E в десятичные градусы"""
        if not coords_str:
            return None, None
        
        try:
            # Удаляем возможные пробелы и приводим к верхнему регистру
            coords_str = coords_str.replace(" ", "").upper()
            
            # Определяем формат по длине строки
            if len(coords_str) == 11:
                # Формат DDMMNDDDMME (градусы и минуты)
                lat_deg = int(coords_str[0:2])
                lat_min = int(coords_str[2:4])
                lat_dir = coords_str[4]
                lat_sec = 0
                
                lon_deg = int(coords_str[5:8])
                lon_min = int(coords_str[8:10])
                lon_dir = coords_str[10]
                lon_sec = 0
                
            elif len(coords_str) == 15:
                # Формат DDMMSSNDDDMMSSE (градусы, минуты и секунды)
                lat_deg = int(coords_str[0:2])
                lat_min = int(coords_str[2:4])
                lat_sec = int(coords_str[4:6])
                lat_dir = coords_str[6]
                
                lon_deg = int(coords_str[7:10])
                lon_min = int(coords_str[10:12])
                lon_sec = int(coords_str[12:14])
                lon_dir = coords_str[14]
                
            else:
                logger.warning(f"⚠️ Неподдерживаемый формат координат: {coords_str} (длина: {len(coords_str)})")
                return None, None

            # Конвертация в десятичные градусы
            lat = lat_deg + lat_min / 60.0 + lat_sec / 3600.0
            if lat_dir == "S":
                lat = -lat

            lon = lon_deg + lon_min / 60.0 + lon_sec / 3600.0
            if lon_dir == "W":
                lon = -lon

            return lon, lat  # (lon, lat) для GeoPandas
            
        except Exception as e:
            logger.error(f"❌ Ошибка парсинга координат '{coords_str}': {e}")
            return None, None
    
    def find_region_by_coords(self, coords_str):
        """Находит регион по компактным координатам используя GeoJSON"""
        if not coords_str:
            return None
        
        # Парсим координаты в десятичные градусы
        lon, lat = self.parse_compact_coords_to_decimal(coords_str)
        if lon is None or lat is None:
            return None
        
        # Создаем точку
        point = Point(lon, lat)
        
        # Ищем регион, содержащий точку
        for region_id, region_data in self.regions_map.items():
            try:
                if region_data['geometry'].contains(point):
                    logger.debug(f"✅ Найден регион {region_id} для координат {coords_str}")
                    return region_id
            except Exception as e:
                logger.warning(f"⚠️ Ошибка проверки региона {region_data['name']}: {e}")
                continue
        
        logger.debug(f"❌ Регион не найден для координат {coords_str}")
        return None

def recreate_table_if_schema_changed(engine):
    """Пересоздает таблицу если схема изменилась"""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = 'public' AND table_name = :table_name
            ORDER BY ordinal_position;
        """), {"table_name": TABLE_NAME})
        current_columns = {row[0]: row[1] for row in result}

        schema_changed = False
        for col, dtype in DESIRED_COLUMNS.items():
            base_type = dtype.split()[0].upper()
            if col not in current_columns or current_columns[col].upper() != base_type:
                schema_changed = True
                break

        if schema_changed:
            logger.info("🔄 Схема изменилась — пересоздаём таблицу...")
            conn.execute(text(f"DROP TABLE IF EXISTS {TABLE_NAME};"))
            
            columns_def = ",\n    ".join([f"{col} {dtype}" for col, dtype in DESIRED_COLUMNS.items()])
            create_sql = f"""
                CREATE TABLE {TABLE_NAME} (
                    {columns_def}
                );
            """
            conn.execute(text(create_sql))
            
            conn.execute(text(f"""
                CREATE INDEX idx_flights_region_id 
                ON {TABLE_NAME} (takeoff_region_id);
            """))
            
            conn.commit()
            logger.info(f"✅ Таблица '{TABLE_NAME}' пересоздана.")
        else:
            logger.info(f"✅ Таблица '{TABLE_NAME}' актуальна.")

def parse_dof(dof_str):
    """Парсит дату из формата YYMMDD"""
    if not dof_str or len(dof_str) != 6:
        return None
    try:
        year = 2000 + int(dof_str[:2])
        return f"{year}-{dof_str[2:4]}-{dof_str[4:6]}"
    except:
        return None

def extract_time_from_code(code):
    """Извлекает время из кода"""
    if not code:
        return None
    clean = ''.join(filter(str.isdigit, str(code)))
    if len(clean) >= 4:
        time_digits = clean[-4:]
        if time_digits.isdigit():
            hour, minute = time_digits[:2], time_digits[2:4]
            if hour.isdigit() and minute.isdigit():
                h, m = int(hour), int(minute)
                if 0 <= h <= 23 and 0 <= m <= 59:
                    return f"{hour}:{minute}"
    return None

def calculate_flight_duration(takeoff_time, landing_time, dof):
    """Вычисляет продолжительность полета в минутах"""
    if not all([takeoff_time, landing_time, dof]):
        return None
    try:
        t_off = datetime.strptime(takeoff_time, "%H:%M")
        t_land = datetime.strptime(landing_time, "%H:%M")
        base_date = datetime.strptime(dof, "%Y-%m-%d")

        takeoff_dt = base_date.replace(hour=t_off.hour, minute=t_off.minute)
        landing_dt = base_date.replace(hour=t_land.hour, minute=t_land.minute)

        if landing_dt <= takeoff_dt:
            landing_dt += timedelta(days=1)

        duration = (landing_dt - takeoff_dt).total_seconds() / 60
        return int(round(duration))
    except:
        return None

def update_takeoff_regions_geojson(engine, region_finder):
    """Обновляет регионы вылета используя GeoJSON"""
    logger.info("🌍 Определение регионов вылета по координатам (GeoJSON)...")
    
    # Загружаем регионы
    if not region_finder.load_regions():
        logger.error("❌ Не удалось загрузить регионы, пропускаем определение")
        return
    
    with engine.connect() as conn:
        # Получаем записи без определенного региона
        result = conn.execute(text(f"""
            SELECT id, takeoff_coords 
            FROM {TABLE_NAME} 
            WHERE takeoff_coords IS NOT NULL 
              AND takeoff_region_id IS NULL
            LIMIT 10000
        """))
        records = result.fetchall()

        if not records:
            logger.info("✅ Все регионы уже определены или нет координат для обработки.")
            return

        logger.info(f"🔍 Найдено {len(records)} записей с координатами для обработки...")
        
        updated = 0
        errors = 0
        no_region_found = 0
        
        for row in records:
            flight_id, coords_str = row
            if not coords_str:
                continue

            try:
                # Ищем регион используя GeoJSON
                region_id = region_finder.find_region_by_coords(coords_str)
                
                if region_id is not None:
                    # Обновляем запись в базе данных
                    conn.execute(
                        text(f"""
                            UPDATE {TABLE_NAME} 
                            SET takeoff_region_id = :region_id
                            WHERE id = :id
                        """),
                        {
                            "region_id": region_id,
                            "id": flight_id
                        }
                    )
                    updated += 1
                else:
                    no_region_found += 1
                
                if (updated + no_region_found) % 100 == 0:
                    logger.info(f"📊 Обработано {updated + no_region_found} записей...")
                    
            except Exception as e:
                logger.warning(f"⚠️ Ошибка при обработке записи {flight_id}: {e}")
                errors += 1

        conn.commit()
        logger.info(f"✅ Обновлено {updated} записей с регионами вылета.")
        logger.info(f"❌ Не найдено регионов для {no_region_found} записей.")
        if errors > 0:
            logger.warning(f"⚠️ Ошибок при обработке: {errors}")

def get_region_statistics(engine):
    """Выводит статистику по регионам"""
    logger.info("\n📊 Статистика по регионам:")
    
    try:
        with engine.connect() as conn:
            # Общее количество записей
            result = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE takeoff_coords IS NOT NULL"))
            total_with_coords = result.scalar()
            logger.info(f"📈 Всего записей с координатами: {total_with_coords}")
            
            # Количество записей с определенными регионами
            result = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE takeoff_region_id IS NOT NULL"))
            total_with_regions = result.scalar()
            logger.info(f"📈 Записей с определенными регионами: {total_with_regions}")

            # Количество записей без регионов
            result = conn.execute(text(f"SELECT COUNT(*) FROM {TABLE_NAME} WHERE takeoff_coords IS NOT NULL AND takeoff_region_id IS NULL"))
            total_without_regions = result.scalar()
            logger.info(f"📈 Записей без определенных регионов: {total_without_regions}")

            # Количество полетов по регионам
            result = conn.execute(text(f"""
                SELECT r.region, COUNT(f.id) as flight_count
                FROM {REGIONS_TABLE} r
                LEFT JOIN {TABLE_NAME} f ON r.id = f.takeoff_region_id
                GROUP BY r.id, r.region
                HAVING COUNT(f.id) > 0
                ORDER BY flight_count DESC
                LIMIT 20;
            """))
            
            logger.info("┌────────────────────────────────┬──────────────┐")
            logger.info("│ Регион                         │ Кол-во полётов │")
            logger.info("├────────────────────────────────┼──────────────┤")
            
            has_data = False
            for row in result:
                region_name = row[0] if row[0] else "Не определен"
                count = row[1] if row[1] else 0
                region_display = region_name[:30] + "..." if len(region_name) > 30 else region_name
                logger.info(f"│ {region_display:<30} │ {count:>12} │")
                has_data = True
            
            if not has_data:
                logger.info("│          Нет данных о полётах           │")
            
            logger.info("└────────────────────────────────┴──────────────┘")
            
    except Exception as e:
        logger.error(f"❌ Ошибка получения статистики: {e}")

def process_flight_data_excel(file_path, original_filename):
    """Основная функция обработки данных о полетах из Excel файла"""
    start_time = time.time()
    
    try:
        # === ПОДКЛЮЧЕНИЕ К БД ===
        try:
            engine = create_engine(DB_URL)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("✅ Подключение к БД успешно.")
        except Exception as e:
            logger.error(f"❌ Ошибка подключения: {e}")
            return {"success": False, "error": f"Ошибка подключения к БД: {e}"}

        # === ПОДГОТОВКА ТАБЛИЦЫ ===
        recreate_table_if_schema_changed(engine)

        # === ЧТЕНИЕ EXCEL ФАЙЛА ===
        try:
            df = pd.read_excel(file_path)
            logger.info(f"✅ Файл Excel загружен: {len(df)} записей")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки Excel файла: {e}")
            return {"success": False, "error": f"Ошибка загрузки Excel файла: {e}"}

        # === НАСТРОЙКА ПАРСЕРОВ ===
        column_parsers = {}
        for col in df.columns:
            col_lower = col.strip().lower()
            if col_lower == "shr":
                column_parsers[col] = shr_pars
            elif col_lower in ("dep", "arr"):
                column_parsers[col] = dep_arr_pars
            else:
                logger.info(f"⚠️  Столбец '{col}' не распознан, будет пропущен.")

        # === ОБРАБОТКА ДАННЫХ И ЗАПИСЬ В БД ===
        inserted_records = 0
        stats = {
            "total_processed": 0,
            "valid_dep_coords": 0,
            "valid_dest_coords": 0,
            "corrected_coords": 0
        }

        logger.info(f"\n🔄 Начинаем обработку {len(df)} записей...")

        with engine.connect() as conn:
            for idx, row in df.iterrows():


                stats["total_processed"] += 1
                
                if stats["total_processed"] % 1000 == 0:
                    logger.info(f"📊 Обработано {stats['total_processed']} записей...")

                # === ПАРСИНГ ДАННЫХ ===
                parsed_data = {}
                for col_name, parser_func in column_parsers.items():
                    value = row[col_name]
                    parsed = parser_func(value)
                    parsed_data[col_name] = parsed

                # === ОБРАБОТКА КООРДИНАТ С ПРИОРИТЕТОМ ===
                shr_data = parsed_data.get('SHR', {})
                dep_data = parsed_data.get('DEP', {})
                arr_data = parsed_data.get('ARR', {})
                
                # КООРДИНАТЫ ВЫЛЕТА
                dep_coords = get_best_coords(
                    dep_data.get('ADEPZ'),
                    shr_data.get('DEP'),
                    shr_data.get('service_line_coords')
                )
                
                # КООРДИНАТЫ ПОСАДКИ
                dest_coords = get_best_coords(
                    arr_data.get('ADARRZ'),
                    shr_data.get('DEST')
                )
                
                # Статистика
                if dep_coords:
                    stats["valid_dep_coords"] += 1
                if dest_coords:
                    stats["valid_dest_coords"] += 1
                if (dep_coords and not shr_data.get('DEP')) or (dest_coords and not shr_data.get('DEST')):
                    stats["corrected_coords"] += 1

                # === ПОДГОТОВКА ДАННЫХ ДЛЯ БД ===
                flight_id = shr_data.get("flight_id") or None
                sid = shr_data.get("SID") or None
                
                if not (flight_id or sid):
                    continue  # Пропускаем записи без идентификаторов

                dof = parse_dof(shr_data.get("DOF"))

                # Время вылета
                takeoff_time = None
                if dep_data and dep_data.get("ATD"):
                    takeoff_time = extract_time_from_code(dep_data["ATD"])
                if not takeoff_time and shr_data.get("start"):
                    takeoff_time = extract_time_from_code(shr_data["start"])

                # Время посадки
                landing_time = None
                if arr_data and arr_data.get("ATA"):
                    landing_time = extract_time_from_code(arr_data["ATA"])
                if not landing_time and shr_data.get("end"):
                    landing_time = extract_time_from_code(shr_data["end"])

                duration = calculate_flight_duration(takeoff_time, landing_time, dof)

                # === ЗАПИСЬ В БД ===
                try:
                    conn.execute(
                        text(f"""
                            INSERT INTO {TABLE_NAME} (
                                flight_id, dof, opr, reg, typ, typ_desc, sid, source_file,
                                takeoff_time, landing_time, takeoff_coords, landing_coords,
                                takeoff_region_id, flight_duration_minutes
                            ) VALUES (
                                :flight_id, :dof, :opr, :reg, :typ, :typ_desc, :sid, :source_file,
                                :takeoff_time, :landing_time, :takeoff_coords, :landing_coords,
                                NULL, :flight_duration_minutes
                            )
                        """),
                        {
                            "flight_id": flight_id,
                            "dof": dof,
                            "opr": shr_data.get("OPR") or None,
                            "reg": shr_data.get("REG") or None,
                            "typ": shr_data.get("TYP") or None,
                            "typ_desc": TYP_DESCRIPTIONS.get(shr_data.get("TYP"), shr_data.get("TYP")) if shr_data.get("TYP") else None,
                            "sid": sid,
                            "source_file": original_filename,
                            "takeoff_time": takeoff_time,
                            "landing_time": landing_time,
                            "takeoff_coords": dep_coords,  # Важно: сохраняем как takeoff_coords
                            "landing_coords": dest_coords, # Важно: сохраняем как landing_coords
                            "flight_duration_minutes": duration
                        }
                    )
                    inserted_records += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Ошибка при вставке записи {idx}: {e}")
                    continue

            conn.commit()

        # === ОПРЕДЕЛЕНИЕ РЕГИОНОВ ===
        region_finder = RegionFinder()  # Теперь без параметра
        update_takeoff_regions_geojson(engine, region_finder)

        # === РАСЧЕТ МЕТРИК ===
        logger.info("📊 Запуск расчета метрик...")
        metrics_result = calculate_metrics()
        if metrics_result["success"]:
            logger.info(f"✅ Метрики рассчитаны для {metrics_result['regions_count']} регионов")
        else:
            logger.warning(f"⚠️ Не удалось рассчитать метрики: {metrics_result.get('error', 'Неизвестная ошибка')}")

        # === СТАТИСТИКА ===
        end_time = time.time()
        elapsed = end_time - start_time
        
        logger.info(f"\n{'='*60}")
        logger.info("📊 ИТОГОВАЯ СТАТИСТИКА")
        logger.info('='*60)
        logger.info(f"Всего обработано записей: {stats['total_processed']}")
        logger.info(f"Успешно загружено в БД: {inserted_records}")
        logger.info(f"Корректные координаты вылета: {stats['valid_dep_coords']}")
        logger.info(f"Корректные координаты посадки: {stats['valid_dest_coords']}")
        logger.info(f"Исправлено координат: {stats['corrected_coords']}")
        logger.info(f"⏱ Время выполнения: {elapsed:.2f} секунд")
        logger.info('='*60)

        # Статистика по регионам
        get_region_statistics(engine)

        logger.info("🎉 Обработка завершена!")

        return {
            "success": True,
            "flights_count": inserted_records,
            "regions_count": stats.get("valid_dep_coords", 0),
            "database_updated": True,
            "metrics_calculated": metrics_result["success"],
            "statistics": stats,
            "summary": {
                "message": f"Обработано {inserted_records} полетов",
                "processing_time": f"{elapsed:.2f} секунд",
                "coordinates_stats": {
                    "valid_departure": stats["valid_dep_coords"],
                    "valid_destination": stats["valid_dest_coords"],
                    "corrected": stats["corrected_coords"]
                }
            }
        }
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки данных о полетах: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # Файл НЕ удаляем, так как он теперь постоянный
        pass