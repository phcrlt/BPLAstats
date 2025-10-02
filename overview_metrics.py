from sqlalchemy import create_engine, text
import json
from config import DB_URL

# === Настройки подключения к БД ===

def get_overview_metrics(db_url=DB_URL):
    """
    Получает общую аналитику по всем регионам:
    - total_flights
    - avg_duration (мин)
    - total_duration (мин → ч)
    - regions_with_flights
    - top_regions (топ-5 по количеству полётов)
    """
    engine = create_engine(db_url)
    
    with engine.connect() as conn:
        # 1. Общее количество полётов
        total_flights = conn.execute(text("SELECT COUNT(*) FROM flights")).scalar() or 0

        # 2. Средняя длительность полёта (только где не NULL)
        avg_duration = conn.execute(text("""
            SELECT ROUND(AVG(flight_duration_minutes), 2)
            FROM flights
            WHERE flight_duration_minutes IS NOT NULL
        """)).scalar() or 0.0

        # 3. Общее время полётов (в минутах → переводим в часы позже)
        total_duration_minutes = conn.execute(text("""
            SELECT COALESCE(SUM(flight_duration_minutes), 0)
            FROM flights
        """)).scalar() or 0

        # 4. Количество регионов с полётами
        regions_with_flights = conn.execute(text("""
            SELECT COUNT(DISTINCT takeoff_region_id)
            FROM flights
            WHERE takeoff_region_id IS NOT NULL
        """)).scalar() or 0

        # 5. Топ-5 регионов по количеству полётов
        top_regions = []
        result = conn.execute(text("""
            SELECT region_name, flight_count
            FROM region_basic_metrics
            WHERE flight_count > 0
            ORDER BY flight_count DESC
            LIMIT 5
        """))
        for row in result:
            top_regions.append({
                "region_name": row[0],
                "flight_count": row[1]
            })

    # Формируем ответ
    return {
        "total_flights": int(total_flights),
        "avg_duration": float(avg_duration),
        "total_duration": int(total_duration_minutes),  # в минутах (фронт сам переведёт в часы)
        "regions_with_flights": int(regions_with_flights),
        "top_regions": top_regions
    }

# === Для тестирования напрямую ===
if __name__ == "__main__":
    metrics = get_overview_metrics()
    print(json.dumps(metrics, ensure_ascii=False, indent=2))