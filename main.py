# uvicorn main:app --reload --host 0.0.0.0 --port 8000
 
# main.py

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
import os
import json
from datetime import datetime
import uuid
import shutil
import pandas as pd
from map_builder import process_geojson_file, get_last_map
from shapefile_processor import process_shapefile
from flight_data_processor import process_flight_data_excel
from metrics_calculator import BasicMetricsCalculator, calculate_metrics
import traceback
from sqlalchemy import text
from overview_metrics import get_overview_metrics
import tempfile

# Импортируем настройки из config
from config import DB_URL, UPLOADS_FOLDER

app = FastAPI()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, UPLOADS_FOLDER)
SHAPEFILE_DIR = os.path.join(BASE_DIR, "shapefile_uploads")
FLIGHT_DATA_DIR = os.path.join(BASE_DIR, "flight_data_uploads")

# Создаем директории для загрузок, если они не существуют
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(SHAPEFILE_DIR, exist_ok=True)
os.makedirs(FLIGHT_DATA_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open(os.path.join(BASE_DIR, "templates", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
    

@app.get("/metrics/all_regions")
async def get_all_regions_metrics():
    """Получает метрики для всех регионов в формате для общей аналитики"""
    try:
        calculator = BasicMetricsCalculator(DB_URL)
        metrics = calculator.get_all_regions_metrics()
        return JSONResponse(metrics)
    except Exception as e:
        print(f"Ошибка получения метрик всех регионов: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/last_map")
async def get_last_processed_map():
    """Возвращает последнюю обработанную карту"""
    try:
        last_map = get_last_map()
        if last_map:
            return JSONResponse(last_map)
        else:
            return JSONResponse({"error": "Нет сохраненных карт"}, status_code=404)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка загрузки карты: {str(e)}")

@app.post("/process")
async def process_uploaded_file(file: UploadFile = File(...)):
    """Обрабатывает загруженные файлы (GeoJSON или Shapefile)"""
    
    # Проверяем расширение файла
    filename_lower = file.filename.lower()
    
    if filename_lower.endswith((".json", ".geojson")):
        return await process_geojson_file_handler(file)
    elif filename_lower.endswith((".shp", ".shx", ".dbf", ".prj", ".zip")):
        return await process_shapefile_handler(file)
    else:
        raise HTTPException(
            status_code=400, 
            detail="Поддерживаются только .json, .geojson, .shp, .shx, .dbf, .prj и .zip файлы"
        )

@app.post("/process_flights")
async def process_flight_data_file(file: UploadFile = File(...)):
    """Обрабатывает загруженные файлы с данными о полетах (XLSX)"""
    
    if not file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400, 
            detail="Поддерживаются только .xlsx и .xls файлы"
        )
    
    result = await process_flight_data_handler(file)
    
    if result.get("success"):
        try:
            metrics_result = calculate_metrics()
            if metrics_result["success"]:
                print(f"✅ Метрики автоматически рассчитаны для {metrics_result['regions_count']} регионов")
            else:
                print(f"⚠️ Не удалось рассчитать метрики: {metrics_result.get('error')}")
        except Exception as e:
            print(f"⚠️ Ошибка при автоматическом расчете метрик: {e}")
    
    return JSONResponse(result)

@app.post("/calculate_metrics")
async def calculate_basic_metrics():
    """Запускает расчет базовых метрик"""
    try:
        print("🚀 Запуск расчета метрик...")
        result = calculate_metrics(DB_URL)  # Явно передаем DB_URL
        
        if result["success"]:
            print(f"✅ Метрики успешно рассчитаны для {result['regions_count']} регионов")
            return JSONResponse({
                "success": True,
                "message": f"Метрики рассчитаны для {result['regions_count']} регионов",
                "regions_count": result['regions_count']
            })
        else:
            print(f"❌ Ошибка расчета метрик: {result.get('error')}")
            return JSONResponse({
                "success": False,
                "error": result.get("error", "Неизвестная ошибка"),
                "message": "Метрики не были рассчитаны"
            })
    except Exception as e:
        error_msg = f"💥 Критическая ошибка расчета метрик: {str(e)}"
        print(error_msg)
        return JSONResponse({
            "success": False,
            "error": str(e),
            "message": "Ошибка расчета метрик"
        })

@app.get("/metrics/region/{region_id}")
async def get_region_metrics(region_id: int):
    """Получает метрики для конкретного региона"""
    try:
        calculator = BasicMetricsCalculator(DB_URL)
        
        metrics = calculator.get_region_metrics(region_id)
        if not metrics:
            raise HTTPException(status_code=404, detail="Метрики для региона не найдены")
        
        return JSONResponse({
            "region_id": metrics[1],
            "region_name": metrics[2],
            "flight_count": metrics[3],
            "avg_duration_minutes": float(metrics[4]) if metrics[4] else 0,
            "total_duration_minutes": metrics[5],
            "peak_load_per_hour": metrics[6],
            "avg_daily_flights": float(metrics[7]) if metrics[7] else 0,
            "median_daily_flights": float(metrics[8]) if metrics[8] else 0,
            "flight_density": float(metrics[9]) if metrics[9] else 0,
            "time_distribution": {
                "morning": metrics[10],
                "day": metrics[11],
                "evening": metrics[12],
                "night": metrics[13]
            },
            "last_calculated": metrics[14].isoformat() if metrics[14] else None
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка получения метрик: {str(e)}")

@app.get("/metrics/overall")
async def get_overall_metrics():
    try:
        metrics = get_overview_metrics()
        return JSONResponse(metrics)
    except Exception as e:
        print(f"Ошибка получения общей аналитики: {e}")
        return JSONResponse({
            "total_flights": 0,
            "avg_duration": 0.0,
            "total_duration": 0,
            "regions_with_flights": 0,
            "top_regions": []
        })

@app.get("/metrics/regions")
async def get_all_regions_metrics():
    """Получает метрики для всех регионов"""
    try:
        calculator = BasicMetricsCalculator(DB_URL)
        
        metrics = calculator.get_all_regions_metrics()
        
        # Добавляем проверку на существование данных
        if not metrics:
            return JSONResponse([])
        
        return JSONResponse(metrics)
    except Exception as e:
        print(f"Ошибка получения метрик регионов: {str(e)}")
        return JSONResponse({"error": str(e)}, status_code=500)
    
@app.get("/debug/regions")
async def debug_regions():
    """Отладочная информация о регионах"""
    try:
        calculator = BasicMetricsCalculator(DB_URL)
        
        with calculator.engine.connect() as conn:
            # Получаем все регионы из базы
            result = conn.execute(text("SELECT id, region FROM russia_regions ORDER BY id"))
            db_regions = [{"id": row[0], "name": row[1]} for row in result]
            
            return JSONResponse({
                "database_regions": db_regions,
                "total_regions": len(db_regions)
            })
    except Exception as e:
        return JSONResponse({"error": str(e)})
    

@app.get("/find_region_by_name")
async def find_region_by_name(region_name: str):
    """Находит ID региона по имени"""
    try:
        calculator = BasicMetricsCalculator(DB_URL)
        
        with calculator.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id FROM russia_regions WHERE LOWER(region) = LOWER(:region_name)"),
                {"region_name": region_name}
            )
            region = result.fetchone()
            
            if region:
                return JSONResponse({"region_id": region[0], "found": True})
            else:
                # Пробуем найти частичное совпадение
                result = conn.execute(
                    text("SELECT id, region FROM russia_regions WHERE LOWER(region) LIKE LOWER(:pattern)"),
                    {"pattern": f"%{region_name}%"}
                )
                partial_match = result.fetchone()
                
                if partial_match:
                    return JSONResponse({
                        "region_id": partial_match[0], 
                        "found": True,
                        "actual_name": partial_match[1],
                        "note": "partial_match"
                    })
                else:
                    return JSONResponse({"found": False})
                    
    except Exception as e:
        return JSONResponse({"error": str(e), "found": False})

async def process_geojson_file_handler(file: UploadFile):
    """Обработчик GeoJSON файлов"""
    # Всегда сохраняем как russia_regions.geojson (ПЕРЕЗАПИСЫВАЕМ!)
    file_path = os.path.join(UPLOAD_DIR, "russia_regions.geojson")

    try:
        # Читаем и сохраняем файл (ПЕРЕЗАПИСЫВАЕМ!)
        content = await file.read()
        
        # Сохраняем файл на диск (перезаписываем если существует)
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Пытаемся прочитать как JSON для проверки валидности
        try:
            input_data = json.loads(content.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Некорректный JSON файл: {str(e)}")

        # Проверяем, что это FeatureCollection
        if not isinstance(input_data, dict) or input_data.get("type") != "FeatureCollection":
            raise HTTPException(status_code=400, detail="Ожидается GeoJSON FeatureCollection")

        # Проверяем наличие features
        if 'features' not in input_data or not input_data['features']:
            raise HTTPException(status_code=400, detail="GeoJSON не содержит features")

        # Логируем информацию о загружаемом файле
        print(f"Обработка GeoJSON файла: {file.filename}")
        print(f"Количество features: {len(input_data['features'])}")
        print(f"Файл сохранен как: {file_path}")
        
        # Обрабатываем файл через функцию из map_builder с ПРИНУДИТЕЛЬНЫМ ОБНОВЛЕНИЕМ
        plotly_data = process_geojson_file(input_data, force_refresh=True)
        
        return JSONResponse({
            **plotly_data,
            "file_info": {
                "original_filename": file.filename,
                "saved_as": "russia_regions.geojson",
                "file_type": "geojson",
                "regions_count": len(input_data['features']),
                "upload_time": datetime.now().isoformat()
            }
        })
        
    except HTTPException:
        raise
    except Exception as e:
        # Удаляем файл в случае ошибки
        if os.path.exists(file_path):
            os.remove(file_path)
        
        # Логируем полную ошибку для отладки
        error_details = traceback.format_exc()
        print(f"Ошибка обработки GeoJSON файла: {str(e)}")
        print(f"Детали ошибки: {error_details}")
        
        raise HTTPException(status_code=500, detail=f"Ошибка обработки файла: {str(e)}")

async def process_shapefile_handler(file: UploadFile):
    """Обработчик Shapefile файлов - использует временную папку только для обработки"""
    # Создаем временную папку для обработки
    temp_dir = tempfile.mkdtemp()
    
    try:
        # Читаем и сохраняем файл во временную папку
        content = await file.read()
        file_path = os.path.join(temp_dir, file.filename)
        
        with open(file_path, "wb") as f:
            f.write(content)

        print(f"Обработка Shapefile компонента: {file.filename}")
        
        # Обрабатываем файл
        if file.filename.lower().endswith('.zip'):
            result = process_shapefile(file_path, file.filename)
        else:
            # Для отдельных компонентов ищем .shp файл
            shp_file = None
            for file_in_dir in os.listdir(temp_dir):
                if file_in_dir.lower().endswith('.shp'):
                    shp_file = os.path.join(temp_dir, file_in_dir)
                    break
            
            if not shp_file:
                return JSONResponse({
                    "status": "waiting_for_components",
                    "message": "Загружены не все компоненты shapefile"
                })
            
            result = process_shapefile(shp_file, file.filename)
        
        if result.get("success"):
            return JSONResponse({
                **result["plotly_data"],
                "file_info": {
                    "original_filename": file.filename,
                    "file_type": "shapefile",
                    "regions_count": result.get("regions_count", 0),
                    "database_updated": result.get("database_updated", False),
                    "upload_time": datetime.now().isoformat()
                }
            })
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Неизвестная ошибка"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки shapefile: {str(e)}")
    finally:
        # Всегда удаляем временную папку после обработки
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)

async def process_zip_shapefile(zip_path: str, session_dir: str, original_filename: str):
    """Обрабатывает ZIP архив с shapefile"""
    try:
        # Обрабатываем shapefile через process_shapefile
        result = process_shapefile(zip_path, original_filename)
        
        if result.get("success"):
            return JSONResponse({
                **result["plotly_data"],
                "file_info": {
                    "original_filename": original_filename,
                    "file_type": "shapefile_zip",
                    "regions_count": result.get("regions_count", 0),
                    "database_updated": result.get("database_updated", False),
                    "upload_time": datetime.now().isoformat()
                }
            })
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Неизвестная ошибка обработки shapefile"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки ZIP архива: {str(e)}")

async def process_single_shapefile_component(file_path: str, session_dir: str, original_filename: str):
    """Обрабатывает отдельный компонент shapefile"""
    try:
        # Для отдельных компонентов shapefile, мы ожидаем, что все файлы будут загружены
        # в одну сессионную папку. Ищем .shp файл в этой папке.
        shp_file = None
        for file in os.listdir(session_dir):
            if file.lower().endswith('.shp'):
                shp_file = os.path.join(session_dir, file)
                break
        
        if not shp_file:
            # Если .shp файл еще не загружен, сообщаем пользователю
            current_files = [f for f in os.listdir(session_dir)]
            return JSONResponse({
                "status": "waiting_for_components",
                "message": "Загружены не все компоненты shapefile",
                "current_files": current_files,
                "required_files": [".shp", ".shx", ".dbf", ".prj"]
            })
        
        # Обрабатываем shapefile
        result = process_shapefile(shp_file, original_filename)
        
        if result.get("success"):
            return JSONResponse({
                **result["plotly_data"],
                "file_info": {
                    "original_filename": original_filename,
                    "file_type": "shapefile",
                    "regions_count": result.get("regions_count", 0),
                    "database_updated": result.get("database_updated", False),
                    "upload_time": datetime.now().isoformat()
                }
            })
        else:
            raise HTTPException(status_code=500, detail=result.get("error", "Неизвестная ошибка обработки shapefile"))
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка обработки shapefile: {str(e)}")

async def process_flight_data_handler(file: UploadFile):
    """Обработчик файлов с данными о полетах - всегда перезаписывает один файл"""
    # Всегда сохраняем как flights_data.xlsx (ПЕРЕЗАПИСЫВАЕМ!)
    file_extension = os.path.splitext(file.filename)[1]
    file_path = os.path.join(FLIGHT_DATA_DIR, f"flights_data{file_extension}")

    try:
        # Читаем и сохраняем файл (ПЕРЕЗАПИСЫВАЕМ!)
        content = await file.read()
        
        with open(file_path, "wb") as f:
            f.write(content)

        print(f"Обработка файла с данными о полетах: {file.filename}")
        
        # Обрабатываем данные о полетах
        result = process_flight_data_excel(file_path, file.filename)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        # Удаляем файл в случае ошибки
        if os.path.exists(file_path):
            os.remove(file_path)
        
        error_details = traceback.format_exc()
        print(f"Ошибка обработки файла с данными о полетах: {str(e)}")
        print(f"Детали ошибки: {error_details}")
        
        return {
            "success": False,
            "error": f"Ошибка обработки файла с данными о полетах: {str(e)}"
        }