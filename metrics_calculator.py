# metrics_calculator.py

from sqlalchemy import create_engine, text
import logging
from config import DB_URL

logger = logging.getLogger(__name__)

class BasicMetricsCalculator:
    def __init__(self, db_url=DB_URL):
        self.db_url = db_url
        self.engine = create_engine(db_url)

    def create_basic_metrics_table(self):
        """Создает таблицу для хранения метрик по регионам"""
        with self.engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS region_basic_metrics (
                    id SERIAL PRIMARY KEY,
                    region_id INTEGER REFERENCES russia_regions(id),
                    region_name VARCHAR(200) NOT NULL,
                    flight_count INTEGER DEFAULT 0,
                    avg_duration_minutes NUMERIC(10,2) DEFAULT 0,
                    total_duration_minutes INTEGER DEFAULT 0,
                    peak_load_per_hour INTEGER DEFAULT 0,
                    avg_daily_flights NUMERIC(10,2) DEFAULT 0,
                    median_daily_flights NUMERIC(10,2) DEFAULT 0,
                    flight_density NUMERIC(10,4) DEFAULT 0,
                    morning_flights INTEGER DEFAULT 0,
                    day_flights INTEGER DEFAULT 0,
                    evening_flights INTEGER DEFAULT 0,
                    night_flights INTEGER DEFAULT 0,
                    last_calculated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(region_id)
                );
            """))
            conn.commit()

    def calculate_peak_load(self, region_id):
        """Рассчитывает пиковую нагрузку для региона"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT dof, COUNT(*) as daily_flights
                FROM flights 
                WHERE takeoff_region_id = :region_id 
                GROUP BY dof
                ORDER BY daily_flights DESC
                LIMIT 1
            """), {'region_id': region_id})
            
            peak_day = result.fetchone()
            if not peak_day:
                return 0
            
            result = conn.execute(text("""
                SELECT EXTRACT(HOUR FROM CAST(takeoff_time AS TIME)) as hour, COUNT(*) as hourly_count
                FROM flights 
                WHERE takeoff_region_id = :region_id AND dof = :peak_date
                GROUP BY EXTRACT(HOUR FROM CAST(takeoff_time AS TIME))
                ORDER BY hourly_count DESC
                LIMIT 1
            """), {'region_id': region_id, 'peak_date': peak_day[0]})
            
            peak_hour = result.fetchone()
            return peak_hour[1] if peak_hour else 0

    def calculate_daily_dynamics(self, region_id):
        """Рассчитывает среднесуточную динамику для региона"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT COUNT(*) as daily_flights
                FROM flights 
                WHERE takeoff_region_id = :region_id 
                GROUP BY dof
                ORDER BY daily_flights
            """), {'region_id': region_id})
            
            daily_flights = [row[0] for row in result.fetchall()]
            
            if not daily_flights:
                return 0, 0
            
            # Среднее значение
            avg_daily = sum(daily_flights) / len(daily_flights)
            
            # Медиана
            sorted_flights = sorted(daily_flights)
            n = len(sorted_flights)
            if n % 2 == 1:
                median_daily = sorted_flights[n // 2]
            else:
                median_daily = (sorted_flights[n // 2 - 1] + sorted_flights[n // 2]) / 2
            
            return round(avg_daily, 2), round(median_daily, 2)

    def calculate_flight_density(self, region_id, flight_count):
        """Рассчитывает плотность полетов на 1000 км²"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT area_sq_km 
                FROM russia_regions 
                WHERE id = :region_id
            """), {'region_id': region_id})
            
            area = result.scalar()
        
        if area and area > 0 and flight_count > 0:
            density = (flight_count / area) * 1000
            return round(density, 4)
        
        return 0

    def calculate_time_distribution(self, region_id):
        """Рассчитывает распределение полетов по времени суток"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    COUNT(CASE WHEN EXTRACT(HOUR FROM CAST(takeoff_time AS TIME)) BETWEEN 6 AND 11 THEN 1 END) as morning,
                    COUNT(CASE WHEN EXTRACT(HOUR FROM CAST(takeoff_time AS TIME)) BETWEEN 12 AND 17 THEN 1 END) as day,
                    COUNT(CASE WHEN EXTRACT(HOUR FROM CAST(takeoff_time AS TIME)) BETWEEN 18 AND 23 THEN 1 END) as evening,
                    COUNT(CASE WHEN EXTRACT(HOUR FROM CAST(takeoff_time AS TIME)) BETWEEN 0 AND 5 THEN 1 END) as night
                FROM flights 
                WHERE takeoff_region_id = :region_id 
                  AND takeoff_time IS NOT NULL
            """), {'region_id': region_id})
            
            distribution = result.fetchone()
            
            if distribution:
                return distribution[0], distribution[1], distribution[2], distribution[3]
        
        return 0, 0, 0, 0

    def calculate_basic_metrics(self):
        """Рассчитывает и сохраняет метрики по регионам"""
        print("🔄 Создание таблицы для метрик...")
        # Создаем таблицу
        self.create_basic_metrics_table()
        
        with self.engine.connect() as conn:
            # Очищаем таблицу
            conn.execute(text("TRUNCATE TABLE region_basic_metrics RESTART IDENTITY;"))
            
            print("📊 Расчет базовых метрик...")
            # Рассчитываем базовые метрики
            result = conn.execute(text("""
                SELECT 
                    rr.id as region_id,
                    rr.region as region_name,
                    COUNT(f.id) as flight_count,
                    ROUND(AVG(f.flight_duration_minutes)::numeric, 2) as avg_duration_minutes,
                    COALESCE(SUM(f.flight_duration_minutes), 0) as total_duration_minutes
                FROM russia_regions rr
                LEFT JOIN flights f ON rr.id = f.takeoff_region_id
                GROUP BY rr.id, rr.region
                ORDER BY flight_count DESC
            """))
            
            metrics_data = result.fetchall()
            print(f"📈 Найдено {len(metrics_data)} регионов для расчета метрик")
            
            # Сохраняем метрики
            processed_count = 0
            for row in metrics_data:
                region_id = row[0]
                region_name = row[1]
                flight_count = row[2] or 0
                
                print(f"🔍 Обработка региона: {region_name} (ID: {region_id}), полетов: {flight_count}")
                
                # Рассчитываем дополнительные метрики только если есть полеты
                if flight_count > 0:
                    print(f"  📊 Расчет дополнительных метрик для {region_name}...")
                    peak_load = self.calculate_peak_load(region_id)
                    avg_daily, median_daily = self.calculate_daily_dynamics(region_id)
                    flight_density = self.calculate_flight_density(region_id, flight_count)
                    morning, day, evening, night = self.calculate_time_distribution(region_id)
                    
                    print(f"  ✅ Метрики рассчитаны: пик={peak_load}, ср.день={avg_daily}")
                else:
                    peak_load = 0
                    avg_daily = 0
                    median_daily = 0
                    flight_density = 0
                    morning, day, evening, night = 0, 0, 0, 0
                
                conn.execute(text("""
                    INSERT INTO region_basic_metrics 
                    (region_id, region_name, flight_count, avg_duration_minutes, total_duration_minutes, 
                    peak_load_per_hour, avg_daily_flights, median_daily_flights, flight_density,
                    morning_flights, day_flights, evening_flights, night_flights)
                    VALUES (:region_id, :region_name, :flight_count, :avg_duration, :total_duration, 
                            :peak_load, :avg_daily, :median_daily, :flight_density,
                            :morning, :day, :evening, :night)
                """), {
                    'region_id': region_id,
                    'region_name': region_name,
                    'flight_count': flight_count,
                    'avg_duration': row[3] if row[3] is not None else 0,
                    'total_duration': row[4],
                    'peak_load': peak_load,
                    'avg_daily': avg_daily,
                    'median_daily': median_daily,
                    'flight_density': flight_density,
                    'morning': morning,
                    'day': day,
                    'evening': evening,
                    'night': night
                })
                
                processed_count += 1
                if processed_count % 10 == 0:
                    print(f"✅ Обработано {processed_count} регионов...")
            
            conn.commit()
        
        print(f"🎉 Расчет метрик завершен! Обработано {len(metrics_data)} регионов")
        return len(metrics_data)

    def get_region_metrics(self, region_id):
        """Получает метрики для конкретного региона"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT * FROM region_basic_metrics 
                WHERE region_id = :region_id
            """), {'region_id': region_id})
            
            return result.fetchone()

    def get_overall_metrics(self):
        """Получает общие метрики по всем регионам"""
        with self.engine.connect() as conn:
            # Общее количество полетов
            total_flights_result = conn.execute(text("SELECT COUNT(*) FROM flights"))
            total_flights = total_flights_result.scalar() or 0
            
            # Средняя продолжительность полета
            avg_duration_result = conn.execute(text("""
                SELECT ROUND(AVG(flight_duration_minutes)::numeric, 2) 
                FROM flights 
                WHERE flight_duration_minutes IS NOT NULL
            """))
            avg_duration = avg_duration_result.scalar() or 0
            
            # Общее время полетов
            total_duration_result = conn.execute(text("""
                SELECT COALESCE(SUM(flight_duration_minutes), 0) 
                FROM flights
            """))
            total_duration = total_duration_result.scalar() or 0
            
            # Количество регионов с полетами
            regions_with_flights_result = conn.execute(text("""
                SELECT COUNT(DISTINCT takeoff_region_id) 
                FROM flights 
                WHERE takeoff_region_id IS NOT NULL
            """))
            regions_with_flights = regions_with_flights_result.scalar() or 0
            
            # Топ регионы по количеству полетов
            top_regions_result = conn.execute(text("""
                SELECT region_name, flight_count 
                FROM region_basic_metrics 
                WHERE flight_count > 0
                ORDER BY flight_count DESC 
                LIMIT 5
            """))
            top_regions = [{"region_name": row[0], "flight_count": row[1]} for row in top_regions_result.fetchall()]
            
            return {
                'total_flights': total_flights,
                'avg_duration': float(avg_duration),
                'total_duration': total_duration,
                'regions_with_flights': regions_with_flights,
                'top_regions': top_regions
            }

    def get_all_regions_metrics(self):
        """Получает метрики для всех регионов"""
        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    region_id,
                    region_name,
                    flight_count,
                    avg_duration_minutes,
                    total_duration_minutes,
                    peak_load_per_hour,
                    avg_daily_flights,
                    median_daily_flights,
                    flight_density,
                    morning_flights,
                    day_flights,
                    evening_flights,
                    night_flights
                FROM region_basic_metrics 
                ORDER BY flight_count DESC
            """))
            
            regions_metrics = []
            for row in result:
                regions_metrics.append({
                    "region_id": row[0],
                    "region_name": row[1],
                    "flight_count": row[2] or 0,
                    "avg_duration_minutes": float(row[3]) if row[3] else 0,
                    "total_duration_minutes": row[4] or 0,
                    "peak_load_per_hour": row[5] or 0,
                    "avg_daily_flights": float(row[6]) if row[6] else 0,
                    "median_daily_flights": float(row[7]) if row[7] else 0,
                    "flight_density": float(row[8]) if row[8] else 0,
                    "time_distribution": {
                        "morning": row[9] or 0,
                        "day": row[10] or 0,
                        "evening": row[11] or 0,
                        "night": row[12] or 0
                    }
                })
            
            return regions_metrics

def calculate_metrics(db_url=DB_URL):
    """Функция для расчета метрик"""
    print(f"🔧 Расчет метрик с DB_URL: {db_url}")
    
    try:
        calculator = BasicMetricsCalculator(db_url)
        
        # Проверяем подключение к БД
        with calculator.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("✅ Подключение к БД успешно")
        
        # Проверяем наличие данных
        with calculator.engine.connect() as conn:
            flights_count = conn.execute(text("SELECT COUNT(*) FROM flights")).scalar()
            print(f"📊 Всего полетов в базе: {flights_count}")
            
            regions_count = conn.execute(text("SELECT COUNT(*) FROM russia_regions")).scalar()
            print(f"🗺️ Всего регионов в базе: {regions_count}")
        
        if flights_count == 0:
            print("⚠️ Нет данных о полетах для расчета метрик")
            return {"success": False, "error": "Нет данных о полетах в базе данных"}
        
        # Рассчитываем метрики
        print("🔄 Начинаем расчет метрик...")
        count = calculator.calculate_basic_metrics()
        
        print(f"✅ Метрики рассчитаны для {count} регионов")
        logger.info(f"✅ Метрики рассчитаны для {count} регионов")
        
        return {"success": True, "regions_count": count}
        
    except Exception as e:
        error_msg = f"❌ Ошибка расчета метрик: {str(e)}"
        print(error_msg)
        logger.error(error_msg)
        return {"success": False, "error": str(e)}