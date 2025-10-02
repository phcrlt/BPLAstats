// Глобальные переменные для управления состоянием карты
let originalColors = [];
let selectedRegionIndex = null;
let isDragging = false;
let selectedFile = null;
let initialPan = null;
let currentUploadType = 'map'; // 'map' или 'flights'
let regionIdMapping = {}; // Добавляем mapping: { traceIndex: regionId }

// Глобальные переменные для поиска
let allRegions = [];
let currentSuggestions = [];
let selectedSuggestionIndex = -1;
let selectedTraceIndex = null;

// Глобальные переменные для общей аналитики
let allRegionsMetrics = [];
let currentSortColumn = 'name';
let currentSortDirection = 'asc';


/**
 * Инициализация фильтра метрик
 */
function initMetricFilter() {
    const metricFilter = document.getElementById('metric-filter');
    if (metricFilter) {
        metricFilter.addEventListener('change', function() {
            updateRegionsTable();
        });
    }
}

/**
 * Показывает выбранный раздел
 */
function showSection(sectionName) {
    // Скрываем все разделы
    document.querySelectorAll('.content-section').forEach(section => {
        section.classList.remove('active');
    });

    // Показываем нужный
    const targetSection = document.getElementById(sectionName + '-section');
    if (targetSection) {
        targetSection.classList.add('active');
    }

    // Обновляем активный пункт меню
    document.querySelectorAll('.nav-item').forEach(item => {
        item.classList.remove('active');
    });
    const activeNavItem = document.querySelector(`[onclick="showSection('${sectionName}')"]`);
    if (activeNavItem) {
        activeNavItem.classList.add('active');
    }

    // Сохраняем выбор
    localStorage.setItem('currentSection', sectionName);

    // Загрузка данных при необходимости
    if (sectionName === 'overview') {
        setTimeout(loadOverviewData, 100);
    } else if (sectionName === 'analytics') {
        loadMapIfNeeded();
    }
    history.pushState(null, '', `#${sectionName}`);
}

/**
 * Загружает данные для общей аналитики
 */
async function loadOverviewData() {
    try {
        console.log('🔄 Загрузка данных общей аналитики...');
        
        const overviewSection = document.getElementById('overview-section');
        if (!overviewSection || !overviewSection.classList.contains('active')) {
            return;
        }

        showLoadingState();

        // Рассчитываем метрики автоматически
        await calculateMetricsAutomatically();
        
        // Загружаем все данные
        await loadOverallStats();
        await loadTopRegions();
        await loadAllRegionsMetrics();
        
        hideLoadingState();
        
        console.log('✅ Данные общей аналитики загружены');
        
    } catch (error) {
        console.error('❌ Ошибка загрузки данных общей аналитики:', error);
        hideLoadingState();
        showNotification('Ошибка загрузки данных аналитики', 'warning');
    }
}

/**
 * Автоматически рассчитывает метрики
 */
async function calculateMetricsAutomatically() {
    try {
        console.log('🔄 Автоматический расчет метрик...');
        
        const response = await fetch('/calculate_metrics', {
            method: 'POST'
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const result = await response.json();
        
        if (result.success) {
            console.log(`✅ Метрики автоматически рассчитаны`);
        } else {
            console.warn('⚠️ Не удалось автоматически рассчитать метрики:', result.error);
        }
        
    } catch (error) {
        console.warn('⚠️ Ошибка автоматического расчета метрик:', error);
    }
}

/**
 * Показывает состояние загрузки
 */
function showLoadingState() {
    const overviewSection = document.getElementById('overview-section');
    if (!overviewSection) return;
    
    let loadingIndicator = document.getElementById('overview-loading');
    if (!loadingIndicator) {
        loadingIndicator = document.createElement('div');
        loadingIndicator.id = 'overview-loading';
        loadingIndicator.className = 'loading-overlay';
        loadingIndicator.innerHTML = `
            <div class="loading-content">
                <div class="spinner"></div>
                <p>Загрузка данных аналитики...</p>
            </div>
        `;
        overviewSection.appendChild(loadingIndicator);
    }
    
    loadingIndicator.style.display = 'flex';
}

/**
 * Скрывает состояние загрузки
 */
function hideLoadingState() {
    const loadingIndicator = document.getElementById('overview-loading');
    if (loadingIndicator) {
        loadingIndicator.style.display = 'none';
    }
}

/**
 * Загружает общую статистику
 */
async function loadOverallStats() {
    try {
        console.log('📊 Загрузка общей статистики...');
        const response = await fetch('/metrics/overall');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const stats = await response.json();
        console.log('📈 Получена статистика:', stats);
        updateOverallStats(stats);
        
    } catch (error) {
        console.error('❌ Ошибка загрузки общей статистики:', error);
        updateOverallStats({
            total_flights: 0,
            avg_duration: 0,
            regions_with_flights: 0,
            total_duration: 0
        });
    }
}

/**
 * Обновляет отображение общей статистики
 */
function updateOverallStats(stats) {
    console.log('🔄 Обновление отображения статистики:', stats);
    
    // Обновляем основные карточки
    updateStatCard('total-flights', stats.total_flights || 0);
    updateStatCard('avg-duration', stats.avg_duration || 0);
    updateStatCard('active-regions', stats.regions_with_flights || 0);
    
    // Преобразуем минуты в часы для общего времени
    const totalHours = Math.round((stats.total_duration || 0) / 60);
    updateStatCard('total-hours', totalHours);
    
    // Обновляем мини-статистику в сайдбаре
    const miniTotalFlights = document.getElementById('mini-total-flights');
    const miniActiveRegions = document.getElementById('mini-active-regions');
    
    if (miniTotalFlights) {
        miniTotalFlights.textContent = (stats.total_flights || 0).toLocaleString();
    }
    if (miniActiveRegions) {
        miniActiveRegions.textContent = (stats.regions_with_flights || 0).toLocaleString();
    }
}

/**
 * Обновляет отдельную карточку статистики
 */
function updateStatCard(cardId, value) {
    const cardElement = document.getElementById(cardId);
    if (!cardElement) {
        console.warn(`⚠️ Карточка с ID ${cardId} не найдена`);
        return;
    }
    
    // Форматируем значение в зависимости от типа карточки
    let formattedValue = value;
    
    if (cardId === 'total-flights' || cardId === 'active-regions' || cardId === 'total-hours') {
        formattedValue = value.toLocaleString();
    } else if (cardId === 'avg-duration') {
        formattedValue = Math.round(value);
    }
    
    cardElement.textContent = formattedValue;
    console.log(`✅ Карточка ${cardId} обновлена: ${formattedValue}`);
}

/**
 * Загружает топ регионов
 */
async function loadTopRegions() {
    try {
        console.log('🏆 Загрузка топ регионов...');
        const response = await fetch('/metrics/regions');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const regionsData = await response.json();
        
        // Сортируем и берем топ-10
        const topFlights = [...regionsData]
            .sort((a, b) => (b.flight_count || 0) - (a.flight_count || 0))
            .slice(0, 10);
            
        const topDuration = [...regionsData]
            .sort((a, b) => (b.avg_duration_minutes || 0) - (a.avg_duration_minutes || 0))
            .slice(0, 10);
        
        updateTopRegionsLists(topFlights, topDuration);
        
    } catch (error) {
        console.error('❌ Ошибка загрузки топ регионов:', error);
        updateTopRegionsLists([], []);
    }
}

/**
 * Обновляет списки топ регионов
 */
function updateTopRegionsLists(topFlights, topDuration) {
    const flightsList = document.getElementById('top-flights-list');
    const durationList = document.getElementById('top-duration-list');
    
    if (flightsList) {
        if (topFlights.length === 0) {
            flightsList.innerHTML = '<div class="no-data">Нет данных о полетах</div>';
        } else {
            flightsList.innerHTML = topFlights.map((region, index) => `
                <div class="top-region-item">
                    <div class="region-rank">${index + 1}</div>
                    <div class="region-info">
                        <div class="region-name">${region.region_name || 'Неизвестный регион'}</div>
                        <div class="region-value">${(region.flight_count || 0).toLocaleString()} полетов</div>
                    </div>
                </div>
            `).join('');
        }
    }
    
    if (durationList) {
        if (topDuration.length === 0) {
            durationList.innerHTML = '<div class="no-data">Нет данных о длительности</div>';
        } else {
            durationList.innerHTML = topDuration.map((region, index) => `
                <div class="top-region-item">
                    <div class="region-rank">${index + 1}</div>
                    <div class="region-info">
                        <div class="region-name">${region.region_name || 'Неизвестный регион'}</div>
                        <div class="region-value">${Math.round(region.avg_duration_minutes || 0)} мин</div>
                    </div>
                </div>
            `).join('');
        }
    }
}

/**
 * Загружает все метрики регионов для таблицы
 */
async function loadAllRegionsMetrics() {
    try {
        console.log('📋 Загрузка всех метрик регионов...');
        
        const tableBody = document.getElementById('regions-table-body');
        const tableContainer = document.querySelector('.regions-table-container');
        
        // Показываем состояние загрузки
        if (tableContainer) {
            tableContainer.classList.add('loading');
        }
        if (tableBody) {
            tableBody.innerHTML = '';
        }

        const response = await fetch('/metrics/regions');
        
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        
        const regionsMetrics = await response.json();
        console.log('📊 Получены метрики регионов:', regionsMetrics.length);
        
        allRegionsMetrics = regionsMetrics;
        updateRegionsTable();
        
    } catch (error) {
        console.error('❌ Ошибка загрузки метрик регионов:', error);
        allRegionsMetrics = [];
        updateRegionsTable();
    } finally {
        const tableContainer = document.querySelector('.regions-table-container');
        if (tableContainer) {
            tableContainer.classList.remove('loading');
        }
    }
}

/**
 * Обновляет таблицу всех регионов с фильтрацией
 */
function updateRegionsTable() {
    const tableBody = document.getElementById('regions-table-body');
    const metricFilter = document.getElementById('metric-filter');
    const tableHead = document.querySelector('.regions-table thead tr');
    
    if (!tableBody || !metricFilter || !tableHead) {
        console.warn('⚠️ Элементы таблицы не найдены');
        return;
    }

    const currentFilter = metricFilter.value;
    
    // Обновляем заголовки таблицы в зависимости от выбранной метрики
    if (currentFilter === 'all') {
        tableHead.innerHTML = `
            <th class="sortable" onclick="sortTable('name')">Регион <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('flight_count')">Количество полетов <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('avg_duration_minutes')">Ср. длительность <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('total_duration_minutes')">Общее время <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('flight_density')">Плотность полетов <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('avg_daily_flights')">Ср. полетов в день <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('peak_load_per_hour')">Пиковая нагрузка <span class="sort-indicator">↕</span></th>
        `;
        renderAllMetricsTable(tableBody);
    } else {
        tableHead.innerHTML = `
            <th class="sortable" onclick="sortTable('name')">Регион <span class="sort-indicator">↕</span></th>
            <th class="sortable" onclick="sortTable('${currentFilter}')">${getMetricLabel(currentFilter)} <span class="sort-indicator">↕</span></th>
        `;
        renderSingleMetricTable(tableBody, currentFilter);
    }
    
    updateSortIndicators();
}

/**
 * Рендерит таблицу со всеми метриками
 */
function renderAllMetricsTable(tableBody) {
    if (allRegionsMetrics.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="7" class="no-data">Нет данных о регионах</td>
            </tr>
        `;
        return;
    }

    const sortedRegions = sortRegions(allRegionsMetrics, currentSortColumn, currentSortDirection);

    tableBody.innerHTML = sortedRegions.map(region => {
        const flightCount = region.flight_count || 0;
        const avgDuration = Math.round(region.avg_duration_minutes || 0);
        const flightDensity = (region.flight_density || 0).toFixed(4);
        const totalHours = Math.round((region.total_duration_minutes || 0) / 60);
        const avgDaily = (region.avg_daily_flights || 0).toFixed(1);
        const peakLoad = region.peak_load_per_hour || 0;

        return `
            <tr>
                <td>${region.region_name || 'Неизвестный регион'}</td>
                <td class="metric-value flights">${flightCount.toLocaleString()}</td>
                <td class="metric-value duration">${avgDuration} мин</td>
                <td class="metric-value hours">${totalHours} ч</td>
                <td class="metric-value density">${flightDensity}</td>
                <td class="metric-value daily">${avgDaily}</td>
                <td class="metric-value peak">${peakLoad}</td>
            </tr>
        `;
    }).join('');
    
    console.log(`✅ Таблица со всеми метриками обновлена: ${sortedRegions.length} регионов`);
}

/**
 * Рендерит таблицу с одной выбранной метрикой
 */
function renderSingleMetricTable(tableBody, metric) {
    if (allRegionsMetrics.length === 0) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="2" class="no-data">Нет данных о регионах</td>
            </tr>
        `;
        return;
    }

    const sortedRegions = sortRegions(allRegionsMetrics, currentSortColumn, currentSortDirection);

    tableBody.innerHTML = sortedRegions.map(region => {
        const metricValue = getFormattedMetricValue(region, metric);
        const metricClass = getMetricClass(metric);

        return `
            <tr>
                <td>${region.region_name || 'Неизвестный регион'}</td>
                <td class="metric-value ${metricClass}">${metricValue}</td>
            </tr>
        `;
    }).join('');
    
    console.log(`✅ Таблица с метрикой "${getMetricLabel(metric)}" обновлена: ${sortedRegions.length} регионов`);
}

/**
 * Сортирует регионы по выбранному столбцу
 */
function sortRegions(regions, column, direction) {
    const sortedRegions = [...regions].sort((a, b) => {
        let valueA, valueB;
        
        if (column === 'name') {
            valueA = a.region_name || '';
            valueB = b.region_name || '';
            return direction === 'asc' ? 
                valueA.localeCompare(valueB) : 
                valueB.localeCompare(valueA);
        } else {
            valueA = a[column] || 0;
            valueB = b[column] || 0;
            return direction === 'asc' ? valueA - valueB : valueB - valueA;
        }
    });
    
    return sortedRegions;
}

/**
 * Сортирует таблицу по выбранному столбцу
 */
function sortTable(column) {
    if (currentSortColumn === column) {
        // Меняем направление сортировки, если кликаем по той же колонке
        currentSortDirection = currentSortDirection === 'asc' ? 'desc' : 'asc';
    } else {
        // Сортируем по новой колонке по убыванию по умолчанию
        currentSortColumn = column;
        currentSortDirection = 'desc';
    }
    
    updateRegionsTable();
}

/**
 * Обновляет индикаторы сортировки в заголовках таблицы
 */
function updateSortIndicators() {
    const sortIndicators = document.querySelectorAll('.sort-indicator');
    sortIndicators.forEach(indicator => {
        indicator.textContent = '↕';
    });
    
    const currentHeader = document.querySelector(`th[onclick="sortTable('${currentSortColumn}')"] .sort-indicator`);
    if (currentHeader) {
        currentHeader.textContent = currentSortDirection === 'asc' ? '↑' : '↓';
    }
}

/**
 * Возвращает поле метрики для сортировки
 */
function getMetricField(metric) {
    const fieldMap = {
        'flight_count': 'flight_count',
        'avg_duration_minutes': 'avg_duration_minutes',
        'total_duration_minutes': 'total_duration_minutes',
        'avg_daily_flights': 'avg_daily_flights',
        'flight_density': 'flight_density',
        'peak_load_per_hour': 'peak_load_per_hour'
    };
    return fieldMap[metric] || 'flight_count';
}

/**
 * Возвращает отформатированное значение метрики
 */
function getFormattedMetricValue(region, metric) {
    const value = region[getMetricField(metric)] || 0;
    
    switch (metric) {
        case 'flight_count':
            return value.toLocaleString();
        case 'avg_duration_minutes':
            return Math.round(value) + ' мин';
        case 'total_duration_minutes':
            return Math.round(value / 60) + ' ч';
        case 'avg_daily_flights':
            return Number(value).toFixed(1);
        case 'flight_density':
            return Number(value).toFixed(4);
        case 'peak_load_per_hour':
            return value;
        default:
            return value;
    }
}

/**
 * Возвращает класс для стилизации метрики
 */
function getMetricClass(metric) {
    const classMap = {
        'flight_count': 'flights',
        'avg_duration_minutes': 'duration',
        'total_duration_minutes': 'hours',
        'avg_daily_flights': 'daily',
        'flight_density': 'density',
        'peak_load_per_hour': 'peak'
    };
    return classMap[metric] || 'flights';
}

/**
 * Возвращает читаемое название метрики
 */
function getMetricLabel(metric) {
    const labelMap = {
        'flight_count': 'Количество полетов',
        'avg_duration_minutes': 'Средняя длительность',
        'total_duration_minutes': 'Общее время полетов',
        'avg_daily_flights': 'Среднее количество в день',
        'flight_density': 'Плотность полетов',
        'peak_load_per_hour': 'Пиковая нагрузка'
    };
    return labelMap[metric] || 'Метрика';
}



/**
 * Инициализация поисковой системы
 */
function initSearch() {
    const searchInput = document.getElementById('regionSearch');
    const searchClear = document.getElementById('searchClear');
    const searchSuggestions = document.getElementById('searchSuggestions');

    if (!searchInput || !searchClear || !searchSuggestions) {
        console.warn('⚠️ Элементы поиска не найдены');
        return;
    }

    // Загружаем список регионов при инициализации
    loadAllRegions();

    // Обработчик ввода в поисковую строку
    searchInput.addEventListener('input', function(e) {
        const query = e.target.value.trim();
        
        if (query.length === 0) {
            hideSuggestions();
            searchClear.style.display = 'none';
            return;
        }
        
        searchClear.style.display = 'flex';
        showSuggestions(query);
    });

    // Обработчик клавиш в поисковой строке
    searchInput.addEventListener('keydown', function(e) {
        switch(e.key) {
            case 'ArrowDown':
                e.preventDefault();
                navigateSuggestions(1);
                break;
            case 'ArrowUp':
                e.preventDefault();
                navigateSuggestions(-1);
                break;
            case 'Enter':
                e.preventDefault();
                selectCurrentSuggestion();
                break;
            case 'Escape':
                hideSuggestions();
                break;
        }
    });

    // Очистка поиска
    searchClear.addEventListener('click', function() {
        searchInput.value = '';
        searchClear.style.display = 'none';
        hideSuggestions();
        searchInput.focus();
        resetRegionSelection();
    });

    // Закрытие подсказок при клике вне области
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.search-container')) {
            hideSuggestions();
        }
    });

    // Фокус на поисковую строку
    searchInput.addEventListener('focus', function() {
        if (this.value.trim().length > 0) {
            showSuggestions(this.value.trim());
        }
    });
}

/**
 * Загружает все регионы из базы данных
 */
async function loadAllRegions() {
    try {
        const response = await fetch('/debug/regions');
        if (!response.ok) {
            throw new Error('Ошибка загрузки регионов');
        }
        
        const data = await response.json();
        allRegions = data.database_regions || [];
        console.log('✅ Загружено регионов:', allRegions.length);
        
    } catch (error) {
        console.error('❌ Ошибка загрузки списка регионов:', error);
        // Если API недоступно, пробуем получить регионы из текущей карты
        extractRegionsFromMap();
    }
}

/**
 * Извлекает регионы из текущей отображенной карты
 */
function extractRegionsFromMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;
    
    const traces = mapElement._fullData;
    
    if (traces && traces.length > 0) {
        allRegions = traces.map((trace, index) => ({
            id: regionIdMapping[index] || index,
            name: trace.name || `Регион ${index + 1}`,
            type: 'region'
        }));
        console.log('✅ Извлечено регионов из карты:', allRegions.length);
    } else {
        allRegions = [];
        console.warn('⚠️ Не удалось извлечь регионы из карты');
    }
}

/**
 * Показывает подсказки для поискового запроса
 */
function showSuggestions(query) {
    if (allRegions.length === 0) {
        showLoadingSuggestions();
        return;
    }

    const normalizedQuery = query.toLowerCase().trim();
    
    // Фильтруем регионы по запросу
    currentSuggestions = allRegions.filter(region => 
        region.name && region.name.toLowerCase().includes(normalizedQuery)
    ).slice(0, 10); // Ограничиваем 10 подсказками

    displaySuggestions(currentSuggestions);
    selectedSuggestionIndex = -1;
}

/**
 * Показывает индикатор загрузки
 */
function showLoadingSuggestions() {
    const searchSuggestions = document.getElementById('searchSuggestions');
    if (!searchSuggestions) return;
    
    searchSuggestions.innerHTML = `
        <div class="search-loading">
            <i class="fas fa-spinner"></i>
            Загрузка регионов...
        </div>
    `;
    searchSuggestions.style.display = 'block';
}

/**
 * Отображает подсказки
 */
function displaySuggestions(suggestions) {
    const searchSuggestions = document.getElementById('searchSuggestions');
    if (!searchSuggestions) return;
    
    if (suggestions.length === 0) {
        searchSuggestions.innerHTML = `
            <div class="search-suggestion">
                <i class="fas fa-search"></i>
                <span>Регионы не найдены</span>
            </div>
        `;
    } else {
        searchSuggestions.innerHTML = suggestions.map((region, index) => `
            <div class="search-suggestion ${index === selectedSuggestionIndex ? 'active' : ''}" 
                 data-region-id="${region.id}" 
                 data-region-name="${region.name}">
                <i class="fas fa-map-marker-alt"></i>
                <span class="region-name">${region.name}</span>
                <span class="region-type">регион</span>
            </div>
        `).join('');
        
        // Добавляем обработчики клика на подсказки
        searchSuggestions.querySelectorAll('.search-suggestion').forEach((suggestion, index) => {
            suggestion.addEventListener('click', () => {
                selectSuggestion(suggestions[index]);
            });
        });
    }
    
    searchSuggestions.style.display = 'block';
}

/**
 * Скрывает подсказки
 */
function hideSuggestions() {
    const searchSuggestions = document.getElementById('searchSuggestions');
    if (searchSuggestions) {
        searchSuggestions.style.display = 'none';
    }
    selectedSuggestionIndex = -1;
}

/**
 * Навигация по подсказкам с помощью клавиш
 */
function navigateSuggestions(direction) {
    if (currentSuggestions.length === 0) return;
    
    selectedSuggestionIndex += direction;
    
    if (selectedSuggestionIndex < 0) {
        selectedSuggestionIndex = currentSuggestions.length - 1;
    } else if (selectedSuggestionIndex >= currentSuggestions.length) {
        selectedSuggestionIndex = 0;
    }
    
    // Обновляем отображение
    displaySuggestions(currentSuggestions);
    
    // Прокручиваем к выбранному элементу
    const selectedElement = document.querySelector(`.search-suggestion:nth-child(${selectedSuggestionIndex + 1})`);
    if (selectedElement) {
        selectedElement.scrollIntoView({ block: 'nearest' });
    }
}

/**
 * Выбирает текущую подсказку (при нажатии Enter)
 */
function selectCurrentSuggestion() {
    if (selectedSuggestionIndex >= 0 && currentSuggestions[selectedSuggestionIndex]) {
        selectSuggestion(currentSuggestions[selectedSuggestionIndex]);
    } else if (currentSuggestions.length > 0) {
        // Если ничего не выбрано, берем первую подсказку
        selectSuggestion(currentSuggestions[0]);
    }
}

/**
 * Выбирает регион из подсказки
 */
function selectSuggestion(region) {
    const searchInput = document.getElementById('regionSearch');
    if (searchInput) {
        searchInput.value = region.name;
    }
    hideSuggestions();
    
    // Выделяем регион на карте
    selectRegionOnMap(region.id, region.name);
}

/**
 * Выделяет регион на карте по ID (для поиска)
 */
function selectRegionOnMap(regionId, regionName) {
    // Находим traceIndex по regionId
    let traceIndex = null;
    for (const [traceIdx, regId] of Object.entries(regionIdMapping)) {
        if (regId === regionId) {
            traceIndex = parseInt(traceIdx);
            break;
        }
    }
    
    if (traceIndex === null) {
        showNotification(`Регион "${regionName}" не найден на карте`, 'warning');
        return;
    }
    
    // Если кликаем на уже выбранный регион - снимаем выделение
    if (selectedTraceIndex === traceIndex) {
        resetRegionSelection();
    } else {
        // Используем общую функцию выделения
        highlightRegionOnMap(traceIndex, regionId, regionName);
    }
    
    // Прокручиваем к карте если нужно
    const mapWrapper = document.querySelector('.map-wrapper');
    if (mapWrapper) {
        mapWrapper.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center' 
        });
    }
}

// Функции для работы с модальными окнами
function openUploadModal() {
    console.log('🗺️ Открытие модального окна загрузки карты...');
    const modal = document.getElementById('uploadModal');
    if (modal) {
        modal.style.display = 'block';
        modal.classList.add('active');
        resetUploadState();
        currentUploadType = 'map';

        // 🔥 Добавьте эту строку:
        setTimeout(() => {
            initFileUpload();
        }, 50); // небольшая задержка, чтобы DOM точно обновился

        console.log('✅ Модальное окно загрузки карты открыто');
    } else {
        console.error('❌ Модальное окно uploadModal не найдено');
    }
}

function closeUploadModal() {
    const modal = document.getElementById('uploadModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
    resetUploadState();
    console.log('✅ Модальное окно загрузки карты закрыто');
}

function openFlightsUploadModal() {
    console.log('🚀 Открытие модального окна загрузки полетов...');
    
    const modal = document.getElementById('flightsUploadModal');
    if (!modal) {
        console.error('❌ Модальное окно flightsUploadModal не найдено');
        return;
    }
    
    modal.style.display = 'block';
    modal.classList.add('active');
    resetFlightsUploadState();
    currentUploadType = 'flights';
    
    // Переинициализируем обработчики при каждом открытии модального окна
    setTimeout(() => {
        initFlightsFileUpload();
    }, 100);
    
    console.log('✅ Модальное окно загрузки полетов открыто');
}

function closeFlightsUploadModal() {
    const modal = document.getElementById('flightsUploadModal');
    if (modal) {
        modal.style.display = 'none';
        modal.classList.remove('active');
    }
    resetFlightsUploadState();
    console.log('✅ Модальное окно загрузки полетов закрыто');
}

// Закрытие модальных окон при клике вне их
document.addEventListener('click', function(event) {
    const uploadModal = document.getElementById('uploadModal');
    const flightsModal = document.getElementById('flightsUploadModal');
    
    if (event.target === uploadModal) {
        closeUploadModal();
    }
    if (event.target === flightsModal) {
        closeFlightsUploadModal();
    }
});

// Закрытие модальных окон по клавише Escape
document.addEventListener('keydown', function(event) {
    if (event.key === 'Escape') {
        closeUploadModal();
        closeFlightsUploadModal();
    }
});

// Закрытие модальных окон при клике на кнопки закрытия
document.addEventListener('DOMContentLoaded', function() {
    // Добавляем обработчики для кнопок закрытия
    const closeButtons = document.querySelectorAll('.close');
    closeButtons.forEach(button => {
        button.addEventListener('click', function() {
            const modal = this.closest('.modal');
            if (modal && modal.id === 'uploadModal') {
                closeUploadModal();
            } else if (modal && modal.id === 'flightsUploadModal') {
                closeFlightsUploadModal();
            }
        });
    });
});

// Сброс состояния загрузки
function resetUploadState() {
    const fileInput = document.getElementById('fileInput');
    const fileInfo = document.getElementById('fileInfo');
    const progressBar = document.getElementById('progressBar');
    const uploadStatus = document.getElementById('uploadStatus');
    const uploadBtn = document.getElementById('uploadBtn');
    
    if (fileInput) fileInput.value = '';
    if (fileInfo) fileInfo.style.display = 'none';
    if (progressBar) progressBar.style.display = 'none';
    if (uploadStatus) {
        uploadStatus.textContent = '';
        uploadStatus.className = 'upload-status';
    }
    if (uploadBtn) uploadBtn.disabled = true;
    selectedFile = null;
}


function resetFlightsUploadState() {
    const fileInput = document.getElementById('flightsFileInput');
    const fileInfo = document.getElementById('flightsFileInfo');
    const progressBar = document.getElementById('flightsProgressBar');
    const uploadStatus = document.getElementById('flightsUploadStatus');
    const uploadBtn = document.getElementById('flightsUploadBtn');
    
    if (fileInput) fileInput.value = '';
    if (fileInfo) fileInfo.style.display = 'none';
    if (progressBar) progressBar.style.display = 'none';
    if (uploadStatus) {
        uploadStatus.textContent = '';
        uploadStatus.className = 'upload-status';
    }
    if (uploadBtn) uploadBtn.disabled = true;
    selectedFile = null;
}

// Инициализация drag & drop для основного модального окна
function initFileUpload() {
    const dropZone = document.getElementById('dropZone');
    const fileInput = document.getElementById('fileInput');

    console.log('🔧 Инициализация загрузки карты...');

    if (!dropZone || !fileInput) {
        console.error('❌ Элементы загрузки файлов не найдены:', {
            dropZone: !!dropZone,
            fileInput: !!fileInput
        });
        return;
    }

    function preventDefaults(e) {
        e.preventDefault();
    }

    function highlight() {
        dropZone.classList.add('dragover');
        console.log('🎯 DropZone подсвечен');
    }

    function unhighlight() {
        dropZone.classList.remove('dragover');
        console.log('🎯 DropZone снято подсвечивание');
    }

    // Обработчики событий drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    // Обработчик drop
    dropZone.addEventListener('drop', function(e) {
        console.log('📂 Drop событие сработало');
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFiles(files);
    }, false);

    // Обработчик клика по dropZone - ПРОСТОЙ И ПРЯМОЙ
    dropZone.addEventListener('click', function(e) {
        console.log('🖱️ Клик по DropZone');
        e.preventDefault();
        fileInput.click(); // Без stopPropagation!
    }, false);

    // Обработчик изменения файлового input
    fileInput.addEventListener('change', function(e) {
        console.log('📝 FileInput изменен, файлов:', e.target.files.length);
        const files = e.target.files;
        handleFiles(files);
    }, false);

    console.log('✅ Инициализация загрузки карты завершена');
}

/**
 * Инициализация загрузки файлов для модального окна полетов
 */
function initFlightsFileUpload() {
    const dropZone = document.getElementById('flightsDropZone');
    const fileInput = document.getElementById('flightsFileInput');

    console.log('🔧 Инициализация загрузки полетов...');

    if (!dropZone || !fileInput) {
        console.error('❌ Не найдены элементы для загрузки полетов:', {
            dropZone: !!dropZone,
            fileInput: !!fileInput
        });
        return;
    }

    function preventDefaults(e) {
        e.preventDefault();

    }

    function highlight() {
        dropZone.classList.add('dragover');
        console.log('🎯 Flights DropZone подсвечен');
    }

    function unhighlight() {
        dropZone.classList.remove('dragover');
        console.log('🎯 Flights DropZone снято подсвечивание');
    }

    // Обработчики событий drag and drop
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, preventDefaults, false);
    });

    ['dragenter', 'dragover'].forEach(eventName => {
        dropZone.addEventListener(eventName, highlight, false);
    });

    ['dragleave', 'drop'].forEach(eventName => {
        dropZone.addEventListener(eventName, unhighlight, false);
    });

    // Обработчик drop
    dropZone.addEventListener('drop', function(e) {
        console.log('📂 Flights Drop событие сработало');
        const dt = e.dataTransfer;
        const files = dt.files;
        handleFlightsFiles(files);
    }, false);

    // Обработчик клика по dropZone - ПРОСТОЙ И ПРЯМОЙ
    dropZone.addEventListener('click', function(e) {
        console.log('🖱️ Клик по Flights DropZone');
        e.preventDefault();
        fileInput.click();
    }, false);

    // Обработчик изменения файлового input
    fileInput.addEventListener('change', function(e) {
        console.log('📝 Flights FileInput изменен, файлов:', e.target.files.length);
        const files = e.target.files;
        handleFlightsFiles(files);
    }, false);

    console.log('✅ Инициализация загрузки полетов завершена');
}

function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFiles(files);
}

function handleFileSelect(e) {
    handleFiles(e.target.files);
}

function handleFiles(files) {
    if (!files || files.length === 0) return;
    const file = files[0];
    
    console.log('📁 Обработка файла:', file.name);
    
    // Проверка размера файла
    if (!validateFileSize(file)) {
        return;
    }
    
    const fileName = file.name.toLowerCase();
    
    let isSupported = false;
    let errorMessage = '';
    
    if (currentUploadType === 'flights') {
        isSupported = fileName.endsWith('.xlsx') || fileName.endsWith('.xls');
        errorMessage = 'Для данных о полетах поддерживаются только .xlsx и .xls файлы';
    } else {
        const supportedFormats = ['.geojson', '.json', '.shp', '.shx', '.dbf', '.prj', '.zip'];
        isSupported = supportedFormats.some(format => fileName.endsWith(format));
        errorMessage = 'Для карт поддерживаются только .geojson, .json, .shp и .zip файлы';
    }
    
    if (!isSupported) {
        console.warn('❌ Неподдерживаемый формат файла:', fileName);
        showNotification(errorMessage, 'warning');
        return;
    }
    
    selectedFile = file;
    updateFileInfo(file);
    
    const uploadBtn = currentUploadType === 'flights' ? 
        document.getElementById('flightsUploadBtn') : 
        document.getElementById('uploadBtn');
    
    if (uploadBtn) {
        uploadBtn.disabled = false;
    }
    
    console.log('✅ Файл принят к загрузке:', file.name);
}

function handleFlightsFiles(files) {
    console.log('🔄 Обработка файлов полетов...', files);
    
    if (!files || files.length === 0) {
        console.warn('⚠️ Нет файлов для обработки');
        return;
    }
    
    const file = files[0];
    console.log('📄 Обрабатываем файл:', file.name);
    
    // Проверка размера файла
    if (!validateFileSize(file)) {
        return;
    }
    
    const fileName = file.name.toLowerCase();
    console.log('🔍 Проверка формата файла:', fileName);
    
    const isSupported = fileName.endsWith('.xlsx') || fileName.endsWith('.xls');
    
    if (!isSupported) {
        console.warn('❌ Неподдерживаемый формат файла для полетов:', fileName);
        showNotification('Для данных о полетах поддерживаются только .xlsx и .xls файлы', 'warning');
        return;
    }
    
    selectedFile = file;
    console.log('✅ Файл принят:', file.name);
    
    updateFlightsFileInfo(file);
    
    const uploadBtn = document.getElementById('flightsUploadBtn');
    if (uploadBtn) {
        uploadBtn.disabled = false;
    }
}

// Обновление информации о файле
function updateFileInfo(file) {
    const fileInfo = document.getElementById('fileInfo');
    const fileName = document.getElementById('fileName');
    const fileSize = document.getElementById('fileSize');
    const fileType = document.getElementById('fileType');
    
    if (!fileInfo || !fileName || !fileSize || !fileType) return;
    
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    
    const fileExt = file.name.toLowerCase().split('.').pop();
    let typeName = 'Неизвестный формат';
    
    switch(fileExt) {
        case 'geojson':
        case 'json':
            typeName = 'GeoJSON';
            break;
        case 'shp':
            typeName = 'Shapefile';
            break;
        case 'zip':
            typeName = 'ZIP архив (Shapefile)';
            break;
        default:
            typeName = file.type || 'Неизвестный';
    }
    
    fileType.textContent = typeName;
    fileInfo.style.display = 'block';
}

function updateFlightsFileInfo(file) {
    const fileInfo = document.getElementById('flightsFileInfo');
    const fileName = document.getElementById('flightsFileName');
    const fileSize = document.getElementById('flightsFileSize');
    const fileType = document.getElementById('flightsFileType');
    
    if (!fileInfo || !fileName || !fileSize || !fileType) return;
    
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    
    const fileExt = file.name.toLowerCase().split('.').pop();
    let typeName = 'Неизвестный формат';
    
    switch(fileExt) {
        case 'xlsx':
            typeName = 'Excel данные о полетах';
            break;
        case 'xls':
            typeName = 'Excel данные о полетах (старый формат)';
            break;
        default:
            typeName = file.type || 'Неизвестный';
    }
    
    fileType.textContent = typeName;
    fileInfo.style.display = 'block';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

/**
 * Загрузка и обработка файла для основного модального окна
 */
async function uploadFile() {
    if (!selectedFile) {
        showNotification('Выберите файл', 'warning');
        return;
    }

    console.log('🚀 Начало загрузки файла:', selectedFile.name);
    
    const formData = new FormData();
    formData.append("file", selectedFile);

    const progressBar = document.getElementById('progressBar');
    const progress = document.getElementById('progress');
    const uploadStatus = document.getElementById('uploadStatus');

    if (progressBar) progressBar.classList.add('show');
    if (progress) progress.style.width = '10%';
    if (uploadStatus) {
        uploadStatus.textContent = 'Подготовка к загрузке...';
        uploadStatus.className = 'upload-status';
    }

    // Определяем endpoint в зависимости от типа загрузки
    const endpoint = currentUploadType === 'flights' ? '/process_flights' : '/process';

    console.log(`🌐 Отправка запроса на: ${endpoint}`);

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 минут таймаут

        if (progress) progress.style.width = '30%';
        if (uploadStatus) uploadStatus.textContent = 'Отправка файла на сервер...';

        const response = await fetch(endpoint, {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        console.log('📡 Получен ответ от сервера:', response.status);

        if (!response.ok) {
            let errorMessage = `HTTP error! status: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorData.error || errorMessage;
                console.error('❌ Ошибка сервера:', errorData);
            } catch (e) {
                console.error('❌ Ошибка парсинга ошибки:', e);
            }
            throw new Error(errorMessage);
        }

        if (progress) progress.style.width = '70%';
        if (uploadStatus) uploadStatus.textContent = 'Обработка данных...';

        const result = await response.json();
        console.log('✅ Данные успешно обработаны:', result);

        if (progress) progress.style.width = '100%';
        
        if (currentUploadType === 'map') {
            // Обработка карты
            if (uploadStatus) {
                uploadStatus.textContent = 'Карта готова!';
                uploadStatus.className = 'upload-status success';
            }
            
            const fileInfo = result.file_info;
            let successMessage = 'Карта успешно построена';
            
            if (fileInfo && fileInfo.database_updated) {
                successMessage += ' и данные загружены в базу данных';
            }
            
            showNotification(successMessage, 'success');
            
            setTimeout(() => closeUploadModal(), 1000);
            
            // Отрисовываем карту - используем весь result
            console.log('🎨 Начинаем отрисовку карты...');
            renderMap(result);
            
        } else {
            // Обработка данных о полетах
            if (uploadStatus) {
                uploadStatus.textContent = 'Данные обработаны!';
                uploadStatus.className = 'upload-status success';
            }
            
            const fileInfo = result.file_info;
            let successMessage = `Обработано ${fileInfo?.flights_count || 0} записей о полетах`;
            
            if (fileInfo?.database_updated) {
                successMessage += ' и загружены в базу данных';
            }
            
            showNotification(successMessage, 'success');
            
            // Показываем статистику
            if (result.statistics) {
                console.log('📊 Показываем статистику:', result.statistics);
                showFlightStatistics(result.statistics, result.summary);
            }
            
            setTimeout(() => closeFlightsUploadModal(), 2000);
        }
        
        if (result.statistics) {
            updateStatsAfterFlightUpload(result.statistics);
        }

    } catch (err) {
        console.error('💥 Критическая ошибка загрузки:', err);
        
        if (progress) progress.style.width = '100%';
        
        if (err.name === 'AbortError') {
            if (uploadStatus) {
                uploadStatus.textContent = 'Ошибка: Превышено время ожидания (5 минут)';
            }
            showNotification('Сервер не ответил за 5 минут. Попробуйте позже или проверьте размер файла.', 'warning');
        } else {
            if (uploadStatus) {
                uploadStatus.textContent = 'Ошибка: ' + err.message;
            }
            showNotification('Не удалось обработать файл: ' + err.message, 'warning');
        }
        
        if (uploadStatus) {
            uploadStatus.className = 'upload-status error';
        }
    }
}

/**
 * Загрузка и обработка файла для модального окна полетов
 */
async function uploadFlightsFile() {
    if (!selectedFile) {
        showNotification('Выберите файл', 'warning');
        return;
    }

    console.log('🚀 Начало загрузки файла с полетами:', selectedFile.name);
    
    const formData = new FormData();
    formData.append("file", selectedFile);

    const progressBar = document.getElementById('flightsProgressBar');
    const progress = document.getElementById('flightsProgress');
    const uploadStatus = document.getElementById('flightsUploadStatus');

    if (progressBar) progressBar.classList.add('show');
    if (progress) progress.style.width = '10%';
    if (uploadStatus) {
        uploadStatus.textContent = 'Подготовка к загрузке...';
        uploadStatus.className = 'upload-status';
    }

    console.log('🌐 Отправка запроса на: /process_flights');

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 300000); // 5 минут таймаут

        if (progress) progress.style.width = '30%';
        if (uploadStatus) uploadStatus.textContent = 'Отправка файла на сервер...';

        const response = await fetch('/process_flights', {
            method: 'POST',
            body: formData,
            signal: controller.signal
        });

        clearTimeout(timeoutId);

        console.log('📡 Получен ответ от сервера:', response.status);

        if (!response.ok) {
            let errorMessage = `HTTP error! status: ${response.status}`;
            try {
                const errorData = await response.json();
                errorMessage = errorData.detail || errorData.error || errorMessage;
                console.error('❌ Ошибка сервера:', errorData);
            } catch (e) {
                console.error('❌ Ошибка парсинга ошибки:', e);
            }
            throw new Error(errorMessage);
        }

        if (progress) progress.style.width = '70%';
        if (uploadStatus) uploadStatus.textContent = 'Обработка данных о полетах...';

        const result = await response.json();
        console.log('✅ Данные о полетах успешно обработаны:', result);

        if (progress) progress.style.width = '100%';
        
        // Обработка данных о полетах
        if (uploadStatus) {
            uploadStatus.textContent = 'Данные обработаны!';
            uploadStatus.className = 'upload-status success';
        }
        
        const fileInfo = result.file_info;
        let successMessage = `Обработано ${fileInfo?.flights_count || 0} записей о полетах`;
        
        if (fileInfo?.database_updated) {
            successMessage += ' и загружены в базу данных';
        }
        
        showNotification(successMessage, 'success');
        
        // Показываем статистику
        if (result.statistics) {
            console.log('📊 Показываем статистику полетов:', result.statistics);
            showFlightStatistics(result.statistics, result.summary);
        }
        
        setTimeout(() => closeFlightsUploadModal(), 2000);
        
        if (result.statistics) {
            updateStatsAfterFlightUpload(result.statistics);
        }

    } catch (err) {
        console.error('💥 Критическая ошибка загрузки полетов:', err);
        
        if (progress) progress.style.width = '100%';
        
        if (err.name === 'AbortError') {
            if (uploadStatus) {
                uploadStatus.textContent = 'Ошибка: Превышено время ожидания (5 минут)';
            }
            showNotification('Сервер не ответил за 5 минут. Файл может быть слишком большим.', 'warning');
        } else {
            if (uploadStatus) {
                uploadStatus.textContent = 'Ошибка: ' + err.message;
            }
            showNotification('Не удалось обработать файл: ' + err.message, 'warning');
        }
        
        if (uploadStatus) {
            uploadStatus.className = 'upload-status error';
        }
    }
}

/**
 * Проверка доступности сервера
 */
async function checkServerStatus() {
    try {
        console.log('🔍 Проверка доступности сервера...');
        const response = await fetch('/last_map', {
            method: 'GET'
        });
        
        if (response.ok) {
            console.log('✅ Сервер доступен');
            return true;
        } else {
            console.log('⚠️ Сервер ответил с ошибкой:', response.status);
            return false;
        }
    } catch (error) {
        console.error('❌ Сервер недоступен:', error);
        showNotification('Сервер недоступен. Проверьте подключение.', 'warning');
        return false;
    }
}

/**
 * Проверка размера файла перед загрузкой
 */
function validateFileSize(file) {
    const maxSize = 100 * 1024 * 1024; // 100MB
    if (file.size > maxSize) {
        showNotification('Файл слишком большой. Максимальный размер: 100MB', 'warning');
        return false;
    }
    if (file.size === 0) {
        showNotification('Файл пустой', 'warning');
        return false;
    }
    return true;
}

// Показывает статистику по данным о полетах
function showFlightStatistics(statistics, summary) {
    const statsHtml = `
        <div class="statistics-popup">
            <h3><i class="fas fa-chart-bar"></i> Статистика обработки данных о полетах</h3>
            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-number">${statistics.total_processed || 0}</div>
                    <div class="stat-label">Всего обработано</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">${statistics.valid_dep_coords || 0}</div>
                    <div class="stat-label">Координат вылета</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">${statistics.valid_dest_coords || 0}</div>
                    <div class="stat-label">Координат посадки</div>
                </div>
                <div class="stat-item">
                    <div class="stat-number">${statistics.corrected_coords || 0}</div>
                    <div class="stat-label">Исправлено координат</div>
                </div>
            </div>
            <div class="stats-details">
                <p><strong>Время обработка:</strong> ${summary.processing_time || 'N/A'}</p>
                <p><strong>Статус:</strong> ${summary.message || 'Обработка завершена'}</p>
            </div>
        </div>
    `;
    
    const popup = document.createElement('div');
    popup.className = 'notification stats-notification';
    popup.innerHTML = statsHtml;
    popup.style.background = 'var(--success-color)';
    popup.style.maxWidth = '500px';
    popup.style.zIndex = '1000';
    
    document.body.appendChild(popup);
    
    setTimeout(() => {
        if (popup.parentNode) {
            popup.parentNode.removeChild(popup);
        }
    }, 5000);
}

// Работа с картой
function loadLastMap() {
    const mapDiv = document.getElementById('map');
    if (!mapDiv) return;
    
    mapDiv.innerHTML = '<div class="loading"><div class="spinner"></div><span>Загрузка последней карты...</span></div>';

    fetch('/last_map')
        .then(response => {
            if (!response.ok) {
                mapDiv.innerHTML = '<div class="welcome-message"><i class="fas fa-map-marked-alt"></i><h3>Добро пожаловать в систему анализа полетов БПЛА</h3><p>Загрузите GeoJSON или Shapefile для построения интерактивной карты регионов</p><button class="btn-primary" onclick="openUploadModal()"><i class="fas fa-file-upload"></i> Загрузить данные карты</button></div>';
                return;
            }
            return response.json();
        })
        .then(plotlyData => {
            if (plotlyData && !plotlyData.error) {
                renderMap(plotlyData);
                showNotification('Загружена последняя карта', 'success');
            }
        })
        .catch(err => {
            console.log('Нет сохраненной карты или ошибка загрузки:', err);
            mapDiv.innerHTML = '<div class="welcome-message"><i class="fas fa-map-marked-alt"></i><h3>Добро пожаловать в систему анализа полетов БПЛА</h3><p>Загрузите GeoJSON или Shapefile для построения интерактивной карты регионов</p><button class="btn-primary" onclick="openUploadModal()"><i class="fas fa-file-upload"></i> Загрузить данные карты</button></div>';
        });
}

/**
 * Отрисовка карты из Plotly-совместимого JSON с интерактивными функциями
 */
function renderMap(plotlyData) {
    const mapDiv = document.getElementById('map');
    if (!mapDiv) return;
    
    mapDiv.innerHTML = '<div class="loading"><div class="spinner"></div><span>Отрисовка карты...</span></div>';

    try {
        // СБРАСЫВАЕМ СОСТОЯНИЕ ПРИ НОВОЙ КАРТЕ
        originalColors = [];
        selectedRegionIndex = null;
        selectedTraceIndex = null;
        regionIdMapping = {};
        
        originalColors = plotlyData.data.map(trace => trace.fillcolor || '#ccc');
        
        // Сбрасываем mapping
        regionIdMapping = {};
        
        plotlyData.data.forEach((trace, index) => {
            trace.hoverinfo = 'text';
            trace.hoveron = 'fills';
            if (!trace.line) trace.line = { color: 'black', width: 1 };
        });

        // Оптимизированные настройки layout с контрастной подложкой
        const layout = {
            ...plotlyData.layout,
            autosize: true,
            margin: { l: 0, r: 0, b: 0, t: 0, pad: 0 },
            paper_bgcolor: 'rgba(0,0,0,0)',
            plot_bgcolor: 'rgba(0,0,0,0)',
            xaxis: {
                visible: false,
                showgrid: false,
                zeroline: false,
                fixedrange: false,
                range: plotlyData.layout?.xaxis?.range || null
            },
            yaxis: {
                visible: false,
                showgrid: false,
                zeroline: false,
                fixedrange: false,
                scaleanchor: 'x',
                scaleratio: 1,
                range: plotlyData.layout?.yaxis?.range || null
            },
            showlegend: false,
            dragmode: 'pan'
        };

        // Конфигурация с включенным zoom и прокруткой
        const config = {
            displayModeBar: true,
            displaylogo: false,
            modeBarButtonsToRemove: ['select2d', 'lasso2d'],
            modeBarButtonsToAdd: ['zoomIn2d', 'zoomOut2d', 'autoScale2d'],
            scrollZoom: true,
            responsive: true,
            fillFrame: true
        };

        Plotly.newPlot('map', plotlyData.data, layout, config).then(() => {
            console.log('✅ Карта успешно отрисована');

            // Восстанавливаем выделение региона если оно было
            setTimeout(() => {
                restoreRegionSelection();
            }, 500);
            
            // Принудительно устанавливаем размеры после отрисовки
            setTimeout(() => {
                const graph = document.querySelector('#map .plotly-graph-div');
                if (graph) {
                    graph.style.width = '100%';
                    graph.style.height = '100%';
                }
                
                const svg = document.querySelector('#map .main-svg');
                if (svg) {
                    svg.style.width = '100%';
                    svg.style.height = '100%';
                }
            }, 100);
            
            // Загружаем mapping регионов после отрисовки карты
            loadRegionMapping(plotlyData);
            
            enforceDefaultCursor();
            
            const observer = new MutationObserver(() => {
                enforceDefaultCursor();
            });
            observer.observe(document.getElementById('map'), {
                attributes: true,
                subtree: true,
                attributeFilter: ['style', 'class']
            });

            const mapElement = document.getElementById('map');
            
            // Сохраняем текущий выделенный регион
            let currentlySelectedTrace = null;
            
            mapElement.on('plotly_hover', function (eventData) {
                if (!isDragging && eventData.points && eventData.points[0]) {
                    enforceDefaultCursor();
                    const traceIndex = eventData.points[0].curveNumber;
                    
                    // Подсвечиваем только если регион не выбран
                    if (traceIndex !== selectedTraceIndex) {
                        Plotly.restyle('map', {
                            'line.color': 'white',
                            'line.width': 3
                        }, [traceIndex]);
                    }
                }
            });

            mapElement.on('plotly_unhover', function (eventData) {
                if (!isDragging && eventData.points && eventData.points[0]) {
                    enforceDefaultCursor();
                    const traceIndex = eventData.points[0].curveNumber;
                    
                    // Восстанавливаем только если регион не выбран
                    if (traceIndex !== selectedTraceIndex) {
                        Plotly.restyle('map', {
                            'line.color': 'black',
                            'line.width': 1,
                            'fillcolor': originalColors[traceIndex]
                        }, [traceIndex]);
                    }
                }
            });

            mapElement.on('plotly_click', function (eventData) {
                if (!eventData.points || !eventData.points[0]) return;
                
                enforceDefaultCursor();
                const traceIndex = eventData.points[0].curveNumber;
                const regionName = plotlyData.data[traceIndex].name || 'Регион';
                
                // Получаем реальный ID региона из mapping
                const regionId = regionIdMapping[traceIndex];
                
                if (regionId === undefined) {
                    console.warn(`Не найден ID региона для: ${regionName}`);
                    showNoMappingInfo(regionName);
                    return;
                }
                
                console.log(`Клик по региону: ${regionName}, traceIndex: ${traceIndex}, regionId: ${regionId}`);
                
                // Если кликаем на уже выбранный регион - снимаем выделение
                if (selectedTraceIndex === traceIndex) {
                    resetRegionSelection();
                } else {
                    // Выделяем регион
                    highlightRegionOnMap(traceIndex, regionId, regionName);
                }
            });

            // Восстанавливаем обработчики для перетаскивания
            mapElement.on('plotly_relayout', function (eventData) {
                enforceDefaultCursor();
            });

            // Восстанавливаем обработчики мыши
            mapElement.addEventListener('mousedown', handleDragStart);
            document.addEventListener('mouseup', handleDragEnd);
            document.addEventListener('mousemove', function (e) {
                if (isDragging) {
                    enforceDefaultCursor();
                }
            });

            // Разрешаем прокрутку страницы когда курсор не над картой
            mapElement.addEventListener('mouseenter', function() {
                document.body.style.overflow = 'hidden';
            });

            mapElement.addEventListener('mouseleave', function() {
                document.body.style.overflow = 'auto';
            });

        }).catch(err => {
            console.error('❌ Ошибка при отрисовке карты:', err);
            mapDiv.innerHTML = '<div class="loading"><span>Ошибка отрисовки карты: ' + err.message + '</span></div>';
        });
    } catch (error) {
        console.error('❌ Ошибка отрисовки карты:', error);
        mapDiv.innerHTML = '<div class="error">Ошибка отрисовки карты</div>';
    }
}

/**
 * Выделяет регион на карте с ярким контрастным цветом
 */
function highlightRegionOnMap(traceIndex, regionId, regionName) {
    console.log(`Выделение региона: traceIndex=${traceIndex}, regionId=${regionId}, name=${regionName}`);
    
    // Снимаем выделение с предыдущего региона
    if (selectedTraceIndex !== null && selectedTraceIndex !== traceIndex) {
        Plotly.restyle('map', {
            'fillcolor': originalColors[selectedTraceIndex],
            'line.color': 'black',
            'line.width': 1
        }, [selectedTraceIndex]);
        console.log(`Снято выделение с предыдущего региона: traceIndex=${selectedTraceIndex}`);
    }
    
    // Яркие контрастные цвета для выделения
    const highlightColors = {
        fill: '#f8f9faff',    // Яркий оранжево-красный
        line: '#babcbdff',    // Яркий красный
        width: 4            // Толстая линия
    };
    
    // Выделяем новый регион
    Plotly.restyle('map', {
        'fillcolor': highlightColors.fill,
        'line.color': highlightColors.line,
        'line.width': highlightColors.width
    }, [traceIndex]);

    // Сохраняем выбранный регион
    selectedRegionIndex = regionId;
    selectedTraceIndex = traceIndex; // Сохраняем traceIndex
    
    console.log(`Установлено выделение: traceIndex=${traceIndex}, regionId=${regionId}`);

    // Загружаем метрики для региона
    loadRegionMetrics(regionId, regionName);
    
    // Обновляем поисковую строку
    updateSearchInput(regionName);
    
    showNotification(`Выбран регион: ${regionName}`);
}

/**
 * Обновляет поисковую строку при выборе региона
 */
function updateSearchInput(regionName) {
    const searchInput = document.getElementById('regionSearch');
    if (searchInput) {
        searchInput.value = regionName;
    }
}

// Загружает mapping между индексами на карте и ID регионов в базе
async function loadRegionMapping(plotlyData) {
    try {
        const response = await fetch('/debug/regions');
        if (!response.ok) {
            console.error('Ошибка загрузки mapping регионов');
            return;
        }
        
        const debugInfo = await response.json();
        const dbRegions = debugInfo.database_regions || [];
        
        console.log('Регионы из базы данных:', dbRegions);
        console.log('Регионы на карте:', plotlyData.data.map((trace, index) => ({ index, name: trace.name })));
        
        // Создаем mapping: ищем соответствие имен регионов
        plotlyData.data.forEach((trace, traceIndex) => {
            const regionName = trace.name;
            
            // 1. Прямое совпадение
            let dbRegion = dbRegions.find(region => region.name === regionName);
            if (dbRegion) {
                regionIdMapping[traceIndex] = dbRegion.id;
                console.log(`✅ Exact match: ${regionName} -> ${dbRegion.name} (ID: ${dbRegion.id})`);
                return;
            }
            
            // 2. Прямое mapping по известным соответствиям
            dbRegion = findDirectRegionMapping(regionName, dbRegions);
            if (dbRegion) {
                regionIdMapping[traceIndex] = dbRegion.id;
                console.log(`✅ Direct mapping: ${regionName} -> ${dbRegion.name} (ID: ${dbRegion.id})`);
                return;
            }
            
            // 3. Нормализуем названия для сравнения
            const normalizedMapName = normalizeRegionName(regionName);
            
            // Ищем по нормализованным названиям
            dbRegion = dbRegions.find(region => {
                if (!region.name) return false;
                const normalizedDbName = normalizeRegionName(region.name);
                return normalizedMapName === normalizedDbName;
            });
            
            if (dbRegion) {
                regionIdMapping[traceIndex] = dbRegion.id;
                console.log(`✅ Normalized match: ${regionName} -> ${dbRegion.name} (ID: ${dbRegion.id})`);
                return;
            }
            
            // 4. Поиск по синонимам
            dbRegion = findRegionBySynonyms(regionName, dbRegions);
            if (dbRegion) {
                regionIdMapping[traceIndex] = dbRegion.id;
                console.log(`✅ Synonym match: ${regionName} -> ${dbRegion.name} (ID: ${dbRegion.id})`);
                return;
            }
            
            console.warn(`❌ Не найден mapping для региона: ${regionName} (traceIndex: ${traceIndex})`);
        });
        
        console.log('Final region mapping:', regionIdMapping);
        
    } catch (error) {
        console.error('Ошибка загрузки mapping регионов:', error);
    }
}

// Вспомогательные функции для mapping регионов
function normalizeRegionName(name) {
    if (!name) return '';
    
    return name
        .toLowerCase()
        .replace(/ё/g, 'е')
        .replace(/[^a-zа-я0-9]/g, '')
        .replace(/республика/g, '')
        .replace(/автономный/g, '')
        .replace(/округ/g, '')
        .replace(/область/g, '')
        .replace(/край/g, '')
        .replace(/автономная/g, '')
        .replace(/—/g, '')
        .replace(/-/g, '')
        .trim();
}

function findRegionBySynonyms(mapName, dbRegions) {
    const synonymMap = {
        'удмуртскаяреспублика': 'удмуртия',
        'республикаудмуртия': 'удмуртия',
        'чувашскаяреспублика': 'чувашия', 
        'республикачувашия': 'чувашия',
        'карачаевочеркесскаяреспублика': 'карачаевочеркесия',
        'кабардинобалкарскаяреспублика': 'кабардинобалкария',
        'республикасевернаяосетияалания': 'севернаяосетияалания',
        'чеченскаяреспублика': 'чеченскаяреспублика',
        'республикадагестан': 'дагестан',
        'республикататарстан': 'татарстан',
        'республикабашкортостан': 'башкортостан',
        'республикамарийэл': 'марийэл',
        'республикамордовия': 'мордовия',
        'республикакалмыкия': 'калмыкия',
        'республикакарелия': 'карелия',
        'республикакоми': 'коми',
        'республикахакасия': 'хакасия',
        'республикабурятия': 'бурятия',
        'республикатыва': 'тыва',
        'республикаадыгея': 'адыгея',
        'республикаалтай': 'алтай',
        'республикасахаякутия': 'сахаякутия',
        'республикакрым': 'крым',
        'республикаингушетия': 'ингушетия'
    };
    
    const normalizedMapName = normalizeRegionName(mapName);
    const synonym = synonymMap[normalizedMapName];
    
    if (synonym) {
        return dbRegions.find(region => {
            if (!region.name) return false;
            const normalizedDbName = normalizeRegionName(region.name);
            return normalizedDbName.includes(synonym) || synonym.includes(normalizedDbName);
        });
    }
    
    return null;
}

function findDirectRegionMapping(mapName, dbRegions) {
    const directMapping = {
        'Удмуртская Республика': 'Удмуртия',
        'УдмуртскаяРеспублика': 'Удмуртия',
        'Чувашская Республика': 'Чувашия', 
        'ЧувашскаяРеспублика': 'Чувашия',
        'Карачаево-Черкесская Республика': 'Карачаево-Черкесия',
        'Кабардино-Балкарская Республика': 'Кабардино-Балкария',
        'Республика Северная Осетия — Алания': 'Северная Осетия - Алания',
        'Чеченская Республика': 'Чеченская республика',
        'Ханты-Мансийский автономный округ — Югра': 'Ханты-Мансийский автономный округ - Югра',
        'Республика Бурятия': 'Бурятия',
        'Республика Тыва': 'Тыва',
        'Республика Башкортостан': 'Башкортостан',
        'Республика Калмыкия': 'Калмыкия',
        'Республика Татарстан': 'Татарстан',
        'Республика Дагестан': 'Дагестан',
        'Республика Крым': 'Республика Крым',
        'Республика Мордовия': 'Мордовия',
        'Республика Марий Эл': 'Марий Эл',
        'Республика Адыгея': 'Адыгея',
        'Республика Ингушетия': 'Ингушетия'
    };
    
    if (directMapping[mapName]) {
        return dbRegions.find(region => region.name === directMapping[mapName]);
    }
    
    const nameWithoutSpaces = mapName.replace(/\s/g, '');
    if (directMapping[nameWithoutSpaces]) {
        return dbRegions.find(region => region.name === directMapping[nameWithoutSpaces]);
    }
    
    return null;
}

// Показывает информацию об отсутствии mapping'а для региона
function showNoMappingInfo(regionName) {
    const infoDiv = document.getElementById('info');
    if (!infoDiv) return;
    
    infoDiv.innerHTML = `
        <h3 class="info-title"><i class="fas fa-info-circle"></i> ${regionName}</h3>
        <div class="info-content">
            <div class="metric-card" style="background: var(--accent-color);">
                <h3><i class="fas fa-map-marker-alt"></i></h3>
                <p>Регион не найден в базе</p>
            </div>
            <div class="info-section">
                <h4><i class="fas fa-exclamation-triangle"></i> Проблема с сопоставлением</h4>
                <p>Регион <strong>"${regionName}"</strong> есть на карте, но не найден в базе данных регионов.</p>
            </div>
        </div>
    `;
}

/**
 * Загружает метрики для региона
 */
async function loadRegionMetrics(regionId, regionName) {
    try {
        const response = await fetch(`/metrics/region/${regionId}`);
        
        if (!response.ok) {
            if (response.status === 404) {
                showNoDataInfo(regionName);
            } else {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return;
        }
        
        const metrics = await response.json();
        
        if (!metrics || metrics.flight_count === 0) {
            showNoDataInfo(regionName);
        } else {
            updateRegionInfo(metrics, regionName);
        }
        
    } catch (error) {
        console.error('Ошибка загрузки метрик региона:', error);
        showNoDataInfo(regionName);
    }
}

// Показывает информацию об отсутствии данных для региона
function showNoDataInfo(regionName) {
    const infoDiv = document.getElementById('info');
    if (!infoDiv) return;
    
    infoDiv.innerHTML = `
        <h3 class="info-title"><i class="fas fa-info-circle"></i> ${regionName}</h3>
        <div class="info-content">
            <div class="metric-card" style="background: var(--warning-color);">
                <h3><i class="fas fa-database"></i></h3>
                <p>Данные не найдены</p>
            </div>
            <div class="info-section">
                <h4><i class="fas fa-exclamation-triangle"></i> Информация</h4>
                <p>Для региона <strong>"${regionName}"</strong> нет данных о полетах в базе данных.</p>
            </div>
        </div>
    `;
}

/**
 * Сбрасывает выделение региона
 */
function resetRegionSelection() {
    console.log('🔄 Сброс выделения региона', { 
        selectedTraceIndex, 
        selectedRegionIndex,
        originalColorsLength: originalColors.length 
    });
    
    // Проверяем, что есть выбранный регион и оригинальные цвета сохранены
    if (selectedTraceIndex !== null && selectedTraceIndex >= 0) {
        console.log(`Сброс выделения региона: traceIndex=${selectedTraceIndex}`);
        
        // Восстанавливаем оригинальный цвет региона
        if (originalColors[selectedTraceIndex]) {
            console.log(`Восстановление цвета для traceIndex ${selectedTraceIndex}:`, originalColors[selectedTraceIndex]);
            
            Plotly.restyle('map', {
                'fillcolor': originalColors[selectedTraceIndex],
                'line.color': 'black',
                'line.width': 1
            }, [selectedTraceIndex]).catch(err => {
                console.error('Ошибка при восстановлении цвета региона:', err);
            });
        } else {
            console.warn(`Оригинальный цвет не найден для traceIndex ${selectedTraceIndex}`);
            
            // Используем fallback цвет
            Plotly.restyle('map', {
                'fillcolor': '#cccccc',
                'line.color': 'black', 
                'line.width': 1
            }, [selectedTraceIndex]).catch(err => {
                console.error('Ошибка при восстановлении fallback цвета:', err);
            });
        }
    } else {
        console.log('Нет выбранного региона для сброса');
    }
    
    // Всегда сбрасываем переменные, даже если selectedTraceIndex был некорректным
    selectedRegionIndex = null;
    selectedTraceIndex = null;
    
    // Очищаем поисковую строку
    const searchInput = document.getElementById('regionSearch');
    if (searchInput) {
        searchInput.value = '';
        
        // Сбрасываем фокус если нужно
        searchInput.blur();
    }
    
    // Сбрасываем информацию о регионе на первоначальное состояние
    const infoDiv = document.getElementById('info');
    if (infoDiv) {
        infoDiv.innerHTML = `
            <div class="info-content">
                <div class="welcome-region-message">
                    <i class="fas fa-map-marker-alt"></i>
                    <h3>Выберите регион</h3>
                    <p>на карте для просмотра детальной информации о полетах</p>
                </div>
            </div>
        `;
    }
    
    // Скрываем подсказки поиска
    hideSuggestions();
    
    showNotification('Выделение региона сброшено');
    
    // Принудительно обновляем состояние карты
    setTimeout(() => {
        enforceDefaultCursor();
    }, 100);
}

/**
 * Восстанавливает выделение региона после перерисовки карты
 */
function restoreRegionSelection() {
    if (selectedTraceIndex !== null && selectedRegionIndex !== null) {
        console.log('Восстановление выделения региона после перерисовки');
        
        // Находим имя региона по ID
        let regionName = 'Регион';
        for (const [traceIdx, regionId] of Object.entries(regionIdMapping)) {
            if (regionId === selectedRegionIndex) {
                const regionElement = document.querySelector(`[data-region-id="${regionId}"]`);
                regionName = regionElement?.dataset?.regionName || 'Регион';
                break;
            }
        }
        
        // Выделяем регион снова
        highlightRegionOnMap(selectedTraceIndex, selectedRegionIndex, regionName);
    }
}

/**
 * Обновляет информацию о регионе с метриками в стильном оформлении
 */
function updateRegionInfo(metrics, regionName) {
    const infoDiv = document.getElementById('info');
    if (!infoDiv) return;
    
    const timeDistribution = metrics.time_distribution || {
        morning: 0, day: 0, evening: 0, night: 0
    };
    
    const totalTimeFlights = timeDistribution.morning + timeDistribution.day + 
                           timeDistribution.evening + timeDistribution.night;
    
    // Создаем круговую диаграмму для распределения по времени суток
    let timeChartHtml = '';
    if (totalTimeFlights > 0) {
        const timeData = [
            { period: 'Утро', value: timeDistribution.morning, color: '#3498db', icon: '🌅' },
            { period: 'День', value: timeDistribution.day, color: '#f39c12', icon: '☀️' },
            { period: 'Вечер', value: timeDistribution.evening, color: '#e74c3c', icon: '🌇' },
            { period: 'Ночь', value: timeDistribution.night, color: '#2c3e50', icon: '🌙' }
        ];
        
        timeChartHtml = `
            <div class="time-chart-section">
                <h4><i class="fas fa-chart-pie"></i> Распределение по времени суток</h4>
                <div class="time-chart-container">
                    <div class="time-chart">
                        ${timeData.map(item => `
                            <div class="time-chart-item" style="--percentage: ${(item.value / totalTimeFlights) * 100}%; --color: ${item.color}">
                                <div class="time-chart-segment">
                                    <span class="time-icon">${item.icon}</span>
                                </div>
                                <div class="time-chart-info">
                                    <span class="time-period">${item.period}</span>
                                    <span class="time-value">${item.value} полетов</span>
                                    <span class="time-percentage">${Math.round((item.value / totalTimeFlights) * 100)}%</span>
                                </div>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;
    }

    // Форматируем плотность полетов
    const flightDensity = metrics.flight_density || 0;
    const formattedDensity = flightDensity % 1 === 0 ? flightDensity : flightDensity.toFixed(3);

    infoDiv.innerHTML = `
        <div class="region-header">
            <div class="region-title">
                <i class="fas fa-map-marker-alt"></i>
                <h3>${regionName}</h3>
            </div>
            <button class="btn-close" onclick="resetRegionSelection()" title="Сбросить выделение">
                <i class="fas fa-times"></i>
            </button>
        </div>
        
        <div class="region-content">
            <!-- Основная метрика -->
            <div class="main-metric-card">
                <div class="metric-icon">
                    <i class="fas fa-plane"></i>
                </div>
                <div class="metric-content">
                    <div class="metric-value">${(metrics.flight_count || 0).toLocaleString()}</div>
                    <div class="metric-label">Всего полетов</div>
                    <div class="metric-trend">
                        <i class="fas fa-chart-line"></i>
                        <span>Общая активность региона</span>
                    </div>
                </div>
            </div>

            <!-- Группа 1: Основные показатели активности -->
            <div class="metrics-group">
                <h4 class="metrics-group-title">
                    <i class="fas fa-chart-bar"></i>
                    Основные показатели
                </h4>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #3498db, #2980b9)">
                            <i class="fas fa-plane-departure"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${metrics.avg_daily_flights || 0}</div>
                            <div class="metric-card-label">Среднее количество полетов в день</div>
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #2ecc71, #27ae60)">
                            <i class="fas fa-chart-line"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${metrics.median_daily_flights || 0}</div>
                            <div class="metric-card-label">Медианное количество полетов в день</div>
                        </div>
                    </div>
                    
                </div>
            </div>

            <!-- Группа 2: Временные характеристики -->
            <div class="metrics-group">
                <h4 class="metrics-group-title">
                    <i class="fas fa-clock"></i>
                    Временные характеристики
                </h4>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #e74c3c, #c0392b)">
                            <i class="fas fa-hourglass-half"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${metrics.avg_duration_minutes || 0} мин</div>
                            <div class="metric-card-label">Средняя длительность полета</div>
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #f39c12, #d35400)">
                            <i class="fas fa-tachometer-alt"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${metrics.peak_load_per_hour || 0}</div>
                            <div class="metric-card-label">Пиковая нагрузка (полетов в час)</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Группа 3: Географические показатели -->
            <div class="metrics-group">
                <h4 class="metrics-group-title">
                    <i class="fas fa-map"></i>
                    Географические показатели
                </h4>
                <div class="metrics-grid">
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #9b59b6, #8e44ad)">
                            <i class="fas fa-map-marker-alt"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${formattedDensity}</div>
                            <div class="metric-card-label">Плотность полетов</div>
                            <div class="metric-card-subtext">на 1000 км²</div>
                        </div>
                    </div>
                    
                    <div class="metric-card">
                        <div class="metric-card-icon" style="background: linear-gradient(135deg, #1abc9c, #16a085)">
                            <i class="fas fa-expand-arrows-alt"></i>
                        </div>
                        <div class="metric-card-content">
                            <div class="metric-card-value">${Math.round((metrics.total_duration_minutes || 0) / 60)} ч</div>
                            <div class="metric-card-label">Общее время налета</div>
                            <div class="metric-card-subtext">всех полетов</div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Диаграмма распределения по времени -->
            ${timeChartHtml}

            <!-- Дополнительная информация -->
            <div class="info-footer">
                <div class="last-update">
                    <i class="fas fa-history"></i>
                    Последнее обновление: ${new Date().toLocaleDateString('ru-RU')}
                </div>
            </div>

        </div>
    `;
}

// Вспомогательные функции
function enforceDefaultCursor() {
    const mapDiv = document.getElementById('map');
    if (mapDiv) {
        mapDiv.style.cursor = 'default';
        const elements = mapDiv.querySelectorAll('*');
        elements.forEach(el => {
            el.style.cursor = 'default';
        });
    }
}

function handleDragStart() {
    isDragging = true;
    initialPan = {
        x: window.scrollX,
        y: window.scrollY
    };
}

function handleDragEnd() {
    isDragging = false;
}

function showNotification(message, type = 'success') {
    const notification = document.createElement('div');
    notification.className = 'notification';
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        background: ${type === 'success' ? 'var(--success-color)' : type === 'warning' ? 'var(--warning-color)' : 'var(--accent-color)'};
        color: white;
        border-radius: 5px;
        z-index: 10000;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

// Функция для загрузки карты если нужно
function loadMapIfNeeded() {
    const mapDiv = document.getElementById('map');
    if (!mapDiv) return;
    
    // Проверяем, есть ли уже карта или это приветственное сообщение
    if (mapDiv.querySelector('.welcome-message') || 
        mapDiv.innerHTML.includes('Загрузка интерактивной карты') ||
        !mapDiv.querySelector('.plotly-graph-div')) {
        loadLastMap();
    }
}

function updateStatsAfterFlightUpload(statistics) {
    if (statistics && statistics.total_processed) {
        showNotification('Статистика обновлена', 'success');
        setTimeout(() => {
            loadOverallStats();
        }, 1000);
    }
}

// Заглушки для функций действий
function downloadRegionReport(regionId) {
    showNotification('Функция скачивания отчета в разработке', 'info');
}

function showRegionTrends(regionId) {
    showNotification('Функция просмотра трендов в разработке', 'info');
}

/**
 * Инициализация приложения
 */
/**
 * Инициализация приложения
 */
document.addEventListener('DOMContentLoaded', async function () {
    console.log('🚀 Инициализация приложения...');
    
    // Проверяем доступность сервера
    const serverAvailable = await checkServerStatus();
    
    if (serverAvailable) {
        // Показываем раздел аналитики по умолчанию
        const urlHash = window.location.hash.replace('#', '');
        let initialSection = 'analytics';

        if (urlHash === 'overview' || urlHash === 'analytics') {
            initialSection = urlHash;
        } else {
            const saved = localStorage.getItem('currentSection');
            if (saved === 'overview' || saved === 'analytics') {
                initialSection = saved;
            }
        }

        showSection(initialSection);
        
        // Инициализируем все модули
        loadOverallStats();
        initFileUpload(); // Инициализация загрузки карты
        initFlightsFileUpload(); // Инициализация загрузки полетов
        initSearch();
        initMetricFilter();
        
        console.log('✅ Все модули инициализированы');
        
        // Загружаем карту с небольшой задержкой
        setTimeout(() => {
            loadMapIfNeeded();
        }, 100);
        
    } else {
        // Показываем сообщение об ошибке
        const mapDiv = document.getElementById('map');
        if (mapDiv) {
            mapDiv.innerHTML = `
                <div class="error-message">
                    <i class="fas fa-exclamation-triangle"></i>
                    <h3>Сервер недоступен</h3>
                    <p>Проверьте:</p>
                    <ul>
                        <li>Запущен ли сервер FastAPI</li>
                        <li>Доступность базы данных</li>
                        <li>Сетевое подключение</li>
                    </ul>
                    <button class="btn-primary" onclick="location.reload()">
                        <i class="fas fa-redo"></i> Перезагрузить
                    </button>
                </div>
            `;
        }
    }
});