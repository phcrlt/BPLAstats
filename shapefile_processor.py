import os
import geopandas as gpd
import json
import logging
from sqlalchemy import create_engine, text
import tempfile
import zipfile
from map_builder import process_geojson_file
from datetime import datetime
import shutil
from config import DB_URL, UPLOADS_FOLDER

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ShapefileProcessor:
    def __init__(self, db_url=DB_URL):
        self.db_url = db_url
        self.engine = create_engine(db_url)

    def debug_table_creation(self):
        """Метод для отладки создания таблицы"""
        try:
            with self.engine.connect() as conn:
                # Проверяем существование таблицы
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'russia_regions'
                    );
                """))
                exists = result.scalar()
                logger.info(f"Таблица russia_regions существует: {exists}")
                
                if exists:
                    # Проверяем структуру таблицы
                    result = conn.execute(text("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_schema = 'public' AND table_name = 'russia_regions'
                        ORDER BY ordinal_position;
                    """))
                    columns = [f"{row[0]} ({row[1]})" for row in result]
                    logger.info(f"Структура таблицы: {columns}")
                    
                    # Проверяем количество записей
                    result = conn.execute(text("SELECT COUNT(*) FROM russia_regions;"))
                    count = result.scalar()
                    logger.info(f"Количество записей в таблице: {count}")
                
                return exists
                
        except Exception as e:
            logger.error(f"Ошибка при отладке таблицы: {e}")
            return False

    def extract_shapefile(self, file_path):
        """Извлекает shapefile из zip или возвращает путь к существующему файлу"""
        if file_path.lower().endswith('.zip'):
            # Создаем временную директорию для распаковки
            temp_dir = tempfile.mkdtemp()
            logger.info(f"Распаковка ZIP архива в: {temp_dir}")
            
            try:
                # Распаковываем архив
                with zipfile.ZipFile(file_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                logger.info("ZIP архив успешно распакован")
                
                # Ищем .shp файл в распакованных файлах
                shp_files = []
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        if file.lower().endswith('.shp'):
                            shp_files.append(os.path.join(root, file))
                
                if not shp_files:
                    logger.error("В архиве не найден .shp файл")
                    raise ValueError("В архиве не найден .shp файл")
                
                # Берем первый найденный .shp файл
                shp_path = shp_files[0]
                logger.info(f"Найден shapefile: {shp_path}")
                
                return shp_path
                    
            except Exception as e:
                logger.error(f"Ошибка распаковки ZIP архива: {e}")
                # Очищаем временную папку в случае ошибки
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise e
        else:
            # Если это не ZIP, возвращаем путь как есть
            return file_path
    
    def shapefile_to_geojson(self, shapefile_path):
        """Конвертирует shapefile в GeoJSON"""
        # Попытка загрузить с разными кодировками
        encodings = ['utf-8', 'cp1251', 'iso-8859-5', 'koi8-r']
        gdf = None
        used_encoding = 'utf-8'
        region_col = 'region'

        for enc in encodings:
            try:
                logger.info(f"Попытка загрузки с кодировкой: {enc}")
                gdf = gpd.read_file(shapefile_path, encoding=enc)
                
                # Ищем столбец с названиями регионов
                for col in gdf.select_dtypes(include='object').columns:
                    if not gdf[col].dropna().empty:
                        sample = gdf[col].dropna().astype(str).iloc[0]
                        if any(c in sample.lower() for c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя'):
                            region_col = col
                            used_encoding = enc
                            logger.info(f"Найден столбец с названиями: '{region_col}' (кодировка: {enc})")
                            break
                else:
                    continue
                break
            except Exception as e:
                logger.warning(f"Кодировка {enc} не подошла: {e}")
                continue
        else:
            # Fallback: без указания кодировки
            logger.info("Используем автоопределение кодировки")
            gdf = gpd.read_file(shapefile_path)
            # Выбираем первый текстовый столбец как название
            text_cols = gdf.select_dtypes(include='object').columns.tolist()
            region_col = text_cols[0] if text_cols else 'region_name'

        # Приводим CRS к WGS84 (EPSG:4326)
        if gdf.crs is None:
            gdf = gdf.set_crs('EPSG:4326')
            logger.info("Установлен CRS: EPSG:4326")
        elif gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs('EPSG:4326')
            logger.info("Конвертирован в CRS: EPSG:4326")
        else:
            logger.info("CRS уже EPSG:4326")

        # Оставляем только нужные поля
        gdf = gdf[[region_col, 'geometry']].copy()
        gdf.rename(columns={region_col: 'region'}, inplace=True)

        # Исправляем кодировку если нужно
        gdf = self._fix_encoding(gdf, used_encoding)

        # Создаем GeoJSON структуру
        geojson_data = {
            "type": "FeatureCollection",
            "features": []
        }

        for idx, row in gdf.iterrows():
            # Правильное преобразование геометрии в GeoJSON
            if hasattr(row.geometry, '__geo_interface__'):
                geometry_json = row.geometry.__geo_interface__
            else:
                try:
                    from shapely.geometry import mapping
                    geometry_json = mapping(row.geometry)
                except:
                    geometry_json = {
                        "type": "GeometryCollection",
                        "geometries": []
                    }

            feature = {
                "type": "Feature",
                "properties": {
                    "region": row['region']
                },
                "geometry": geometry_json
            }
            geojson_data["features"].append(feature)

        logger.info(f"Создан GeoJSON с {len(gdf)} регионами")
        
        # Показываем примеры названий
        if len(gdf) > 0:
            logger.info("Примеры регионов:")
            for i, region in enumerate(gdf['region'].head(5), 1):
                logger.info(f"   {i}. {region}")
        
        return geojson_data, len(gdf)

    def _fix_encoding(self, gdf, original_encoding):
        """Исправление проблем с кодировкой"""
        sample_text = gdf['region'].iloc[0] if len(gdf) > 0 else ""
        
        # Если текст выглядит как неправильная кодировка
        if 'Р' in str(sample_text) and 'С' in str(sample_text):
            logger.info("Обнаружена проблема с кодировкой, исправляем...")
            
            try:
                fixed_regions = []
                for region in gdf['region']:
                    if region and isinstance(region, str):
                        try:
                            fixed = region.encode('windows-1251').decode('utf-8')
                            fixed_regions.append(fixed)
                        except:
                            fixed_regions.append(region)
                    else:
                        fixed_regions.append(region)
                
                gdf['region'] = fixed_regions
                logger.info("Кодировка исправлена")
                
            except Exception as e:
                logger.warning(f"Не удалось исправить кодировку: {e}")
        
        return gdf

    def create_table_if_not_exists(self):
        """Создает таблицу если она не существует"""
        try:
            with self.engine.connect() as conn:
                # Проверяем существование таблицы
                result = conn.execute(text("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'russia_regions'
                    );
                """))
                table_exists = result.scalar()
                
                if not table_exists:
                    logger.info("Создание таблицы russia_regions...")
                    conn.execute(text("""
                        CREATE TABLE russia_regions (
                            id SERIAL PRIMARY KEY,
                            region VARCHAR(200) NOT NULL,
                            area_sq_km NUMERIC(12, 2),
                            geometry GEOMETRY(Geometry, 4326),
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        );
                    """))
                    
                    # Создаем индексы
                    conn.execute(text("""
                        CREATE INDEX idx_russia_regions_geom 
                        ON russia_regions USING GIST (geometry);
                        
                        CREATE INDEX idx_russia_regions_name 
                        ON russia_regions (region);
                    """))
                    conn.commit()
                    logger.info("✅ Таблица russia_regions создана")
                    return True
                else:
                    logger.info("✅ Таблица russia_regions уже существует")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Ошибка создания таблицы: {e}")
            return False

    def load_to_database(self, geojson_data):
        """Загружает данные в базу данных PostgreSQL с PostGIS"""
        try:
            # Сначала отладочная информация
            logger.info("🔍 Проверка состояния базы данных перед загрузкой...")
            table_exists_before = self.debug_table_creation()
            
            # Создаем таблицу если нужно
            creation_success = self.create_table_if_not_exists()
            if not creation_success:
                logger.error("❌ Не удалось создать таблицу")
                return False
            
            # Проверяем после создания
            logger.info("🔍 Проверка состояния базы данных после создания таблицы...")
            table_exists_after = self.debug_table_creation()
            
            if not table_exists_after:
                logger.error("❌ Таблица все еще не существует после попытки создания")
                return False
            
            # Очищаем таблицу перед загрузкой
            with self.engine.connect() as conn:
                conn.execute(text("TRUNCATE TABLE russia_regions RESTART IDENTITY;"))
                conn.commit()
                logger.info("✅ Таблица очищена")
            
            # Загружаем данные в базу
            inserted_count = 0
            with self.engine.connect() as conn:
                for feature in geojson_data['features']:
                    region_name = feature['properties']['region']
                    geometry_json = json.dumps(feature['geometry'])
                    
                    logger.info(f"Загрузка региона: {region_name}")
                    
                    try:
                        # Используем ST_GeomFromGeoJSON для загрузки геометрии
                        conn.execute(text("""
                            INSERT INTO russia_regions (region, area_sq_km, geometry)
                            VALUES (
                                :region_name,
                                ST_Area(ST_GeomFromGeoJSON(:geometry)::geography) / 1000000.0,
                                ST_GeomFromGeoJSON(:geometry)
                            )
                        """), {
                            'region_name': region_name,
                            'geometry': geometry_json
                        })
                        inserted_count += 1
                    except Exception as e:
                        logger.error(f"❌ Ошибка вставки региона {region_name}: {e}")
                        continue
                
                # Округляем площади
                try:
                    conn.execute(text("""
                        UPDATE russia_regions 
                        SET area_sq_km = ROUND(area_sq_km, 2)
                    """))
                except Exception as e:
                    logger.warning(f"⚠️ Не удалось округлить площади: {e}")
                
                conn.commit()
            
            # Финальная проверка
            logger.info("🔍 Финальная проверка базы данных...")
            self.debug_table_creation()
            
            logger.info(f"✅ Данные загружены в базу: {inserted_count} регионов")
            return inserted_count > 0
            
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки в базу: {e}")
            import traceback
            logger.error(f"Детали ошибки: {traceback.format_exc()}")
            return False


def save_geojson_to_uploads(geojson_data):
    """Сохраняет GeoJSON данные в папку uploads как russia_regions.geojson (ПЕРЕЗАПИСЫВАЕТ!)"""
    try:
        # Создаем папку uploads если её нет
        os.makedirs(UPLOADS_FOLDER, exist_ok=True)
        
        # Путь для сохранения
        geojson_path = os.path.join(UPLOADS_FOLDER, "russia_regions.geojson")
        
        # Сохраняем GeoJSON (ПЕРЕЗАПИСЫВАЕМ!)
        with open(geojson_path, 'w', encoding='utf-8') as f:
            json.dump(geojson_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ GeoJSON сохранен/перезаписан как: {geojson_path}")
        return geojson_path
        
    except Exception as e:
        logger.error(f"❌ Ошибка сохранения GeoJSON: {e}")
        return None


def process_shapefile(file_path, original_filename):
    """Основная функция обработки shapefile"""
    temp_dir = None
    try:
        processor = ShapefileProcessor()
        
        # Извлекаем shapefile если нужно
        shapefile_path = processor.extract_shapefile(file_path)
        logger.info(f"Обрабатывается shapefile: {os.path.basename(shapefile_path)}")
        
        # Конвертируем в GeoJSON
        geojson_data, regions_count = processor.shapefile_to_geojson(shapefile_path)
        
        if regions_count == 0:
            return {
                "success": False,
                "error": "Shapefile не содержит данных"
            }
        
        # Сохраняем GeoJSON в папку uploads
        geojson_path = save_geojson_to_uploads(geojson_data)
        
        # Загружаем в базу данных
        db_success = processor.load_to_database(geojson_data)
        
        # Создаем карту с принудительным обновлением
        plotly_data = process_geojson_file(geojson_data, force_refresh=True)
        
        return {
            "success": True,
            "plotly_data": plotly_data,
            "regions_count": regions_count,
            "database_updated": db_success,
            "geojson_saved": geojson_path is not None
        }
        
    except Exception as e:
        logger.error(f"Ошибка обработки shapefile: {e}")
        return {
            "success": False,
            "error": str(e)
        }
    finally:
        # Очищаем временные файлы
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)