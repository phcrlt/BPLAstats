# map_builder.py

import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.ops import snap, unary_union
from shapely.geometry.polygon import Polygon
from shapely.geometry.multipolygon import MultiPolygon
from tqdm import tqdm
import plotly.graph_objects as go
from shapely.geometry import Point
import plotly.express as px
import os
import logging
import json
import hashlib

# Настройка логирования в файл
logging.basicConfig(
    filename='geometry_processing.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Директория для кэшированных карт
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

def get_file_hash(geojson_data):
    """Генерирует хэш для GeoJSON данных"""
    content = json.dumps(geojson_data, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()

def get_cached_map(file_hash):
    """Пытается получить кэшированную карту"""
    cache_file = os.path.join(CACHE_DIR, f"{file_hash}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                logging.info(f"Загружена кэшированная карта: {file_hash}")
                return json.load(f)
        except Exception as e:
            logging.warning(f"Ошибка загрузки кэша: {e}")
    return None

def save_map_to_cache(file_hash, plotly_data):
    """Сохраняет карту в кэш"""
    try:
        cache_file = os.path.join(CACHE_DIR, f"{file_hash}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(plotly_data, f, ensure_ascii=False)
        logging.info(f"Карта сохранена в кэш: {file_hash}")
        
        # Сохраняем информацию о последнем файле
        last_file_info = {
            'file_hash': file_hash,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        with open(os.path.join(CACHE_DIR, 'last_map.json'), 'w', encoding='utf-8') as f:
            json.dump(last_file_info, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Ошибка сохранения кэша: {e}")

def get_last_map():
    """Возвращает данные последней обработанной карты"""
    try:
        last_file_path = os.path.join(CACHE_DIR, 'last_map.json')
        if os.path.exists(last_file_path):
            with open(last_file_path, 'r', encoding='utf-8') as f:
                last_info = json.load(f)
            
            cache_file = os.path.join(CACHE_DIR, f"{last_info['file_hash']}.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    logging.info("Загружена последняя карта из кэша")
                    return json.load(f)
    except Exception as e:
        logging.warning(f"Ошибка загрузки последней карты: {e}")
    return None

def process_geojson_file(geojson_data):
    """
    Обрабатывает GeoJSON данные и возвращает Plotly-совместимый словарь
    """
    try:
        # Проверяем кэш
        file_hash = get_file_hash(geojson_data)
        cached_map = get_cached_map(file_hash)
        if cached_map:
            return cached_map

        logging.info("Начало обработки GeoJSON данных")
        
        # Создаем GeoDataFrame из переданных данных
        gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
        logging.info(f"Загружено {len(gdf)} регионов из GeoJSON")

        # Определяем поле с названием региона
        region_column = None
        for col in ['region', 'name', 'NAME', 'REGION', 'title', 'properties']:
            if col in gdf.columns:
                region_column = col
                break
        
        if region_column:
            if region_column == 'properties':
                # Если есть поле properties, извлекаем название из него
                gdf['region'] = gdf['properties'].apply(
                    lambda x: x.get('name') or x.get('region') or x.get('NAME') or 'Неизвестный регион'
                )
            else:
                gdf['region'] = gdf[region_column]
        else:
            # Если нет подходящего поля, создаем свои названия
            gdf['region'] = [f"Регион_{i}" for i in range(len(gdf))]
        
        logging.info(f"Используется поле для названий регионов: {region_column}")

        # Устанавливаем CRS если его нет (предполагаем WGS84 для GeoJSON)
        if gdf.crs is None:
            gdf.set_crs('EPSG:4326', inplace=True)
            logging.info("Установлена система координат EPSG:4326")
        else:
            logging.info(f"Исходная система координат: {gdf.crs}")

        # Перевод в систему координат EPSG:32646
        gdf = gdf.to_crs('EPSG:32646')
        logging.info("Переведено в EPSG:32646")

        # Подготовка регионов
        regions = prepare_regions(gdf)

        # Преобразование геометрии для Plotly
        tqdm.pandas(desc='Преобразование геометрии')
        regions[['x', 'y']] = regions.geometry.progress_apply(geom2shape)
        logging.info("Геометрии преобразованы в x, y")

        # Создание карты
        fig = create_map_figure(regions)
        logging.info("Карта успешно создана")

        # Сохраняем результат
        plotly_data = fig.to_dict()
        save_map_to_cache(file_hash, plotly_data)

        return plotly_data

    except Exception as e:
        logging.error(f"Ошибка обработки GeoJSON: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise


def prepare_regions(gdf, area_thr=100e6, simplify_tol=500):
    """
    Подготовка регионов: фильтрация, упрощение, объединение границ
    """
    gdf_ = gdf.copy()

    # Вычисление площади
    gdf_['area'] = gdf_.geometry.apply(lambda x: x.area)
    logging.info("Вычислена площадь регионов")

    # Удаление мелких полигонов
    tqdm.pandas(desc='Удаление мелких полигонов')
    def filter_small_polys(geometry):
        if geometry.geom_type == 'MultiPolygon':
            small_polys = [p for p in geometry.geoms if p.area <= area_thr]
            if small_polys:
                logging.info(f"Удалено {len(small_polys)} полигонов с площадью <= {area_thr}")
            return MultiPolygon([p for p in geometry.geoms if p.area > area_thr])
        return geometry
    
    gdf_.geometry = gdf_.geometry.progress_apply(filter_small_polys)
    logging.info("Мелкие полигоны удалены")

    # Упрощение геометрии
    gdf_.geometry = gdf_.geometry.simplify(simplify_tol)
    logging.info(f"Геометрия упрощена с допуском {simplify_tol}")

    # Объединение границ (упрощенная версия для производительности)
    logging.info("Начало объединения границ")
    geoms = gdf_.geometry.values
    for i in tqdm(range(len(geoms)), desc='Объединение границ'):
        g1 = geoms[i]
        for j in range(len(geoms)):
            if i != j and g1.distance(geoms[j]) < 100:
                g1 = snap(g1, geoms[j], 800)
        geoms[i] = g1
    gdf_.geometry = geoms
    logging.info("Границы объединены")

    # Сортировка по площади
    gdf_ = gdf_.sort_values(by='area', ascending=False).reset_index(drop=True)
    logging.info("Регионы отсортированы")

    return gdf_.drop(columns=['area'])

def geom2shape(g):
    """
    Преобразование геометрии в координаты для Plotly
    """
    try:
        if g.geom_type == 'MultiPolygon':
            x, y = [], []
            for poly in g.geoms:
                if poly.exterior:
                    x_, y_ = poly.exterior.coords.xy
                    x.extend(x_)
                    y.extend(y_)
                    x.append(None)
                    y.append(None)
            if x and y:
                x = x[:-1]  # Убираем последний None
                y = y[:-1]
            return pd.Series([x, y])
        elif g.geom_type == 'Polygon':
            if g.exterior:
                x, y = g.exterior.coords.xy
                return pd.Series([list(x), list(y)])
        return pd.Series([[], []])
    except Exception as e:
        logging.warning(f"Ошибка преобразования геометрии: {e}")
        return pd.Series([[], []])

def create_map_figure(regions):
    """
    Создание Plotly figure из данных регионов
    """
    fig = go.Figure()

    # Выбор палитры Plotly
    colors = px.colors.qualitative.Plotly
    num_colors = len(colors)

    # Отрисовка регионов
    for i, r in regions.iterrows():
        # Проверяем, что есть данные для отрисовки
        if len(r.x) > 0 and len(r.y) > 0:
            region_color = colors[i % num_colors]
            fig.add_trace(go.Scatter(
                x=r.x,
                y=r.y,
                name=r.region,
                text=r.region,
                hoverinfo="text",
                line_color='black',
                fill='toself',
                line_width=1,
                fillcolor=region_color,
                showlegend=False,
                hovertemplate=f'<b>{r.region}</b><extra></extra>',
                hoverlabel=dict(
                    bgcolor='white',
                    font=dict(color='black')
                ),
                hoveron='fills',
                line=dict(
                    color='grey',
                    width=1
                )
            ))

    # Настройка осей
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False, scaleanchor="x", scaleratio=1)

    # Настройка внешнего вида
    fig.update_layout(
        showlegend=False,
        dragmode='pan',
        width=1000,
        height=600,
        margin=dict(l=20, r=20, t=80, b=20, autoexpand=True),
        paper_bgcolor="#b2beca",
        plot_bgcolor="#b2beca",
        hovermode='closest',
        xaxis=dict(fixedrange=False),
        yaxis=dict(fixedrange=False),
        autosize=True,
        template='plotly_white'
    )

    return fig


# Настройка логирования в файл
logging.basicConfig(
    filename='geometry_processing.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Директория для кэшированных карт
CACHE_DIR = os.path.join(os.path.dirname(__file__), 'cache')
os.makedirs(CACHE_DIR, exist_ok=True)

def get_file_hash(geojson_data):
    """Генерирует хэш для GeoJSON данных"""
    content = json.dumps(geojson_data, sort_keys=True)
    return hashlib.md5(content.encode()).hexdigest()

def get_cached_map(file_hash):
    """Пытается получить кэшированную карту"""
    cache_file = os.path.join(CACHE_DIR, f"{file_hash}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                logging.info(f"Загружена кэшированная карта: {file_hash}")
                return json.load(f)
        except Exception as e:
            logging.warning(f"Ошибка загрузки кэша: {e}")
    return None

def save_map_to_cache(file_hash, plotly_data):
    """Сохраняет карту в кэш"""
    try:
        cache_file = os.path.join(CACHE_DIR, f"{file_hash}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(plotly_data, f, ensure_ascii=False)
        logging.info(f"Карта сохранена в кэш: {file_hash}")
        
        # Сохраняем информацию о последнем файле
        last_file_info = {
            'file_hash': file_hash,
            'timestamp': pd.Timestamp.now().isoformat()
        }
        with open(os.path.join(CACHE_DIR, 'last_map.json'), 'w', encoding='utf-8') as f:
            json.dump(last_file_info, f, ensure_ascii=False)
    except Exception as e:
        logging.error(f"Ошибка сохранения кэша: {e}")

def clear_cache():
    """Очищает кэш карт"""
    try:
        for file in os.listdir(CACHE_DIR):
            if file.endswith('.json') and file != 'last_map.json':
                os.remove(os.path.join(CACHE_DIR, file))
        logging.info("Кэш карт очищен")
    except Exception as e:
        logging.error(f"Ошибка очистки кэша: {e}")

def get_last_map():
    """Возвращает данные последней обработанной карты"""
    try:
        last_file_path = os.path.join(CACHE_DIR, 'last_map.json')
        if os.path.exists(last_file_path):
            with open(last_file_path, 'r', encoding='utf-8') as f:
                last_info = json.load(f)
            
            cache_file = os.path.join(CACHE_DIR, f"{last_info['file_hash']}.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    logging.info("Загружена последняя карта из кэша")
                    return json.load(f)
    except Exception as e:
        logging.warning(f"Ошибка загрузки последней карты: {e}")
    return None

def process_geojson_file(geojson_data, force_refresh=False):
    """
    Обрабатывает GeoJSON данные и возвращает Plotly-совместимый словарь
    """
    try:
        # Если force_refresh=True, очищаем кэш
        if force_refresh:
            clear_cache()

        # Проверяем кэш
        file_hash = get_file_hash(geojson_data)
        cached_map = get_cached_map(file_hash)
        if cached_map and not force_refresh:
            return cached_map

        logging.info("Начало обработки GeoJSON данных")
        
        # Создаем GeoDataFrame из переданных данных
        gdf = gpd.GeoDataFrame.from_features(geojson_data['features'])
        logging.info(f"Загружено {len(gdf)} регионов из GeoJSON")

        # Определяем поле с названием региона
        region_column = None
        for col in ['region', 'name', 'NAME', 'REGION', 'title', 'properties']:
            if col in gdf.columns:
                region_column = col
                break
        
        if region_column:
            if region_column == 'properties':
                # Если есть поле properties, извлекаем название из него
                gdf['region'] = gdf['properties'].apply(
                    lambda x: x.get('name') or x.get('region') or x.get('NAME') or 'Неизвестный регион'
                )
            else:
                gdf['region'] = gdf[region_column]
        else:
            # Если нет подходящего поля, создаем свои названия
            gdf['region'] = [f"Регион_{i}" for i in range(len(gdf))]
        
        logging.info(f"Используется поле для названий регионов: {region_column}")

        # Устанавливаем CRS если его нет (предполагаем WGS84 для GeoJSON)
        if gdf.crs is None:
            gdf.set_crs('EPSG:4326', inplace=True)
            logging.info("Установлена система координат EPSG:4326")
        else:
            logging.info(f"Исходная система координат: {gdf.crs}")

        # Перевод в систему координат EPSG:32646
        gdf = gdf.to_crs('EPSG:32646')
        logging.info("Переведено в EPSG:32646")

        # Подготовка регионов
        regions = prepare_regions(gdf)

        # Преобразование геометрии для Plotly
        tqdm.pandas(desc='Преобразование геометрии')
        regions[['x', 'y']] = regions.geometry.progress_apply(geom2shape)
        logging.info("Геометрии преобразованы в x, y")

        # Создание карты
        fig = create_map_figure(regions)
        logging.info("Карта успешно создана")

        # Сохраняем результат
        plotly_data = fig.to_dict()
        save_map_to_cache(file_hash, plotly_data)

        return plotly_data

    except Exception as e:
        logging.error(f"Ошибка обработки GeoJSON: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        raise