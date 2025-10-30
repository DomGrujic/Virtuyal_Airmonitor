/**
 * \file DataMainpage.js
 * \brief Frontend logic for the data main page: load device metadata, poll live measurements, and render charts.
 *
 * \details Documented in JSDoc/JavaDoc style so Doxygen can include it in the combined site.
 * Key responsibilities:
 * - Fetch device list and partition into online/offline
 * - Poll current measurements per device and maintain rolling time series
 * - Render metric tiles and multiple Chart.js visualizations (live and historical)
 * - Provide comparison charts across sensors with selectable metric and time range
 * - Handle basic frontend role checks and conditional admin UI
 *
 * @module DataMainpage
 */

/**
 * Number of sensors displayed in the live charts section.
 * @type {number}
 */
const SENSOR_COUNT = 5;
/**
 * Rolling window size (number of points) maintained for on-page live charts.
 * @type {number}
 */
const WINDOW_SIZE = 5; // Anzahl Datenpunkte im Chart

/**
 * Base URL of the backend API.
 * @type {string}
 */
const baseUrl = (window.location && window.location.origin ? window.location.origin : '') + '/api';

// Simple client-side role helper (frontend guard)
/**
 * Returns whether the current user is an administrator based on localStorage flags.
 * This is a best-effort frontend guard and must not be relied upon for backend authorization.
 * @returns {boolean} True if localStorage indicates an authenticated admin user; otherwise false.
 */
function __isAdmin(){
  try{
    // Require explicit login; otherwise always treat as guest
    const loggedIn = localStorage.getItem('isLoggedIn') === 'true';
    if(!loggedIn) return false;
    const email = (localStorage.getItem('userEmail')||'').toLowerCase();
    const role = (localStorage.getItem('userRole')||'').toLowerCase();
    if(role === 'admin') return true;
  }catch(e){}
  return false;
}
window.__IS_ADMIN__ = __isAdmin;

//class with only device details
/**
 * A sensor with its metadata and rolling time series for Chart visualizations.
 *
 * @class Sensor
 * @param {number} id Internal index for UI lists/tabs.
 * @param {string} deviceId Unique device identifier used by the backend API.
 * @param {string} deviceName Human-readable name for display.
 * @param {string} classroomNumber Room identifier or label.
 * @param {boolean|string|number} status Online/offline status as provided by the API.
 */
class Sensor {
  constructor(id, deviceId, deviceName, classroomNumber, status) {
    this.id = id;
    this.deviceId = deviceId;
    this.deviceName = deviceName;
    this.classroomNumber = classroomNumber;
    this.status = status;
    // Zeitreihen für Charts
    /** @type {string[]} */
    this.timeLabels = [];
    /** @type {number[]} */
    this.tempData = [];
    /** @type {number[]} */
    this.co2Data = [];
    // Weitere Zeitreihen für Vergleich
    /** @type {number[]} */
    this.humidityData = [];
    /** @type {number[]} */
    this.pm25Data = [];
    /** @type {number[]} */
    this.pm10Data = [];
    /** @type {number[]} */
    this.pm03Data = [];
    /** @type {number[]} */
    this.pm1Data = [];
    /** @type {number[]} */
    this.tvocData = [];
    /** @type {number[]} */
    this.aqiData = [];
    /** @type {number[]} */
    this.coData = [];
    /** @type {number[]} */
    this.hchoData = [];
    // Letzte Messwerte (werden bei fetchLatestMeasurements befüllt)
    /** @type {?number} */ this.humidity = null;      // hum
    /** @type {?number} */ this.pm25 = null;          // pm2_5
    /** @type {?number} */ this.pm1_0 = null;         // pm1_0 (Original-Key)
    /** @type {?number} */ this.pm1 = null;           // Alias für Anzeige (wird aus pm1_0 gespiegelt)
    /** @type {?number} */ this.tvoc = null;          // tvoc
    /** @type {?number} */ this.aqi = null;           // aqi
    /** @type {?number} */ this.co = null;            // co
    /** @type {?number} */ this.hcho = null;          // hcho
    /** @type {?number} */ this.pm10 = null;          // pm10
    /** @type {?number} */ this.pm03 = null;          // pm_3 oder pm0_3 (je nach Backend)
    /** @type {?Object} */ this.lastRaw = null;       // vollständiger letzter Roh-Datensatz
  }

  /**
   * Add a new measurement sample to the rolling buffers and update last-known scalar values.
   * Trims all series to {@link WINDOW_SIZE} items.
   * @param {Object<string, (number|null|undefined)>} raw A backend payload containing latest values
   * (e.g. { temp, co2, hum, pm2_5, pm10, pm_3/pm0_3, pm1_0, tvoc, aqi, co, hcho }).
   * @returns {void}
   */
  addMeasurement(raw){
    if(!raw || typeof raw !== 'object') return;
    this.lastRaw = raw; // kompletter Datensatz merken
    // Zeitlabel
    const label = new Date().toLocaleTimeString('de-DE',{ hour:'2-digit', minute:'2-digit'});
    this.timeLabels.push(label);
    // Numerische Zeitreihen nur hinzufügen wenn gültig
    if(typeof raw.temp === 'number') this.tempData.push(raw.temp);
    if(typeof raw.co2 === 'number') this.co2Data.push(raw.co2);
    if(typeof raw.hum === 'number') this.humidityData.push(raw.hum);
    if(typeof raw.pm2_5 === 'number') this.pm25Data.push(raw.pm2_5);
    if(typeof raw.pm10 === 'number') this.pm10Data.push(raw.pm10);
    if(typeof raw.pm_3 === 'number') this.pm03Data.push(raw.pm_3); else if(typeof raw.pm0_3 === 'number') this.pm03Data.push(raw.pm0_3);
    if(typeof raw.pm1_0 === 'number') this.pm1Data.push(raw.pm1_0); else if(typeof raw.pm1 === 'number') this.pm1Data.push(raw.pm1);
    if(typeof raw.tvoc === 'number') this.tvocData.push(raw.tvoc);
    if(typeof raw.aqi === 'number') this.aqiData.push(raw.aqi);
    if(typeof raw.co === 'number') this.coData.push(raw.co);
    if(typeof raw.hcho === 'number') this.hchoData.push(raw.hcho);
    // Einzelwerte aktualisieren (nur überschreiben wenn vorhanden)
    this.humidity = raw.hum ?? this.humidity;
    this.pm25 = raw.pm2_5 ?? this.pm25;
    this.pm1_0 = raw.pm1_0 ?? this.pm1_0;
    this.pm1 = raw.pm1_0 ?? raw.pm1 ?? this.pm1;
    this.tvoc = raw.tvoc ?? this.tvoc;
    this.aqi = raw.aqi ?? this.aqi;
    this.co = raw.co ?? this.co;
    this.hcho = raw.hcho ?? this.hcho;
    this.pm10 = raw.pm10 ?? this.pm10;
    this.pm03 = raw.pm_3 ?? raw.pm0_3 ?? this.pm03;
    // Fenster beschneiden
    while(this.tempData.length > WINDOW_SIZE) this.tempData.shift();
    while(this.co2Data.length > WINDOW_SIZE) this.co2Data.shift();
    const trim = (arr)=>{ while(arr.length>WINDOW_SIZE) arr.shift(); };
    [this.humidityData,this.pm25Data,this.pm10Data,this.pm03Data,this.pm1Data,this.tvocData,this.aqiData,this.coData,this.hchoData].forEach(trim);
    while(this.timeLabels.length > WINDOW_SIZE) this.timeLabels.shift();
  }
}

// Lokale Sensor-Objekte (Mock-Werte, bis Backend lädt)
//dynamisches array von sensor objekt
/** Online sensor instances used for rendering and polling. */
let sensors = [];
/** Offline sensors metadata for UI list. */
let offlineSensors = [];


let activeSensorIndex = 0;

// DOM Elemente
/** Cached DOM element for temperature tile. */
const tempEl = document.getElementById("temperature");
const humEl = document.getElementById("humidity");
const co2El = document.getElementById("co2");
const pm25El = document.getElementById("pm25");
const pm10El = document.getElementById("pm10");
const tvocEl = document.getElementById("tvoc");
const aqiEl = document.getElementById("aqi");
const coEl = document.getElementById("co");
const hchoEl = document.getElementById("hcho");
const pm03El = document.getElementById("pm03");
const pm1El = document.getElementById("pm1");

/**
 * Returns the currently active sensor instance.
 * @returns {Sensor|undefined}
 */
function getActive() {
  return sensors[activeSensorIndex];
}

/**
 * Update the labels showing which sensor is currently active in the UI.
 * @returns {void}
 */
function updateActiveSensorLabels(){
  const s = getActive();
  const label = s ? `${s.deviceName || 'Sensor'}${s.classroomNumber ? ' - '+s.classroomNumber : ''}` : '';
  const elCurrent = document.getElementById('activeSensorLabelCurrent');
  const elCharts  = document.getElementById('activeSensorLabelCharts');
  if(elCurrent) elCurrent.textContent = label;
  if(elCharts)  elCharts.textContent  = label;
}

// ---------------------------------------------------------------
// 1️⃣ Geräte-Metadaten vom Backend abrufen
// ---------------------------------------------------------------
/**
 * Fetch all devices from the backend and build the in-memory sensor lists.
 * Partitions devices into online (limited by {@link SENSOR_COUNT}) and offline for display.
 * Also triggers initial UI rendering and chart updates.
 * @returns {Promise<void>}
 */
async function fetchDevices() {
  try {
    const res = await fetch(`${baseUrl}/sensor/getAllDevices`);
    if (!res.ok) throw new Error("HTTP " + res.status);
    const json = await res.json();
    if (!json.success || !Array.isArray(json.data)) {
      console.warn('Unerwartete Geräte-Antwort', json);
      return;
    }
    const all = json.data || [];
    // Partition into online/offline
    const onlineRaw = [];
    const offlineRaw = [];
    all.forEach((dev) => {
      const rawStatus = (dev.status !== undefined) ? dev.status : dev.Status;
      const isOnline = (rawStatus === true || rawStatus === 'true' || rawStatus === 'online' || rawStatus === 1 || rawStatus === '1');
      if(isOnline) onlineRaw.push(dev); else offlineRaw.push(dev);
    });
    // limit to SENSOR_COUNT online devices for live charts
    const devices = onlineRaw.slice(0, SENSOR_COUNT);
    // Build online sensors array
    sensors = [];
    devices.forEach((dev, i) => {
      const deviceId = dev.device_id || dev.DeviceID || dev.id || dev.deviceId;
      const name = dev.name || dev.Name || dev.device_name || `Sensor ${i+1}`;
      const status = (dev.status !== undefined ? dev.status : dev.Status) ?? 'unknown';
  const classroom = dev.classroom_number || dev.classroomNumber || dev.ClassroomNumber || dev.Classrooms_ClassroomNumber || dev.classrooms_classroomNumber || dev.room || '';
      if(!deviceId){
        console.warn('⚠️ Gerät ohne device_id übersprungen:', dev);
        return;
      }
      const s = new Sensor(i, deviceId, name, classroom, status);
      s.timeLabels = [];
      s.tempData = [];
      s.co2Data = [];
      sensors.push(s);
    });
    // Store offline sensors meta for dropdown
    offlineSensors = offlineRaw.map((dev, j) => ({
      deviceId: dev.device_id || dev.DeviceID || dev.id || dev.deviceId,
      name: dev.name || dev.Name || dev.device_name || `Sensor (offline ${j+1})`,
      classroom: dev.classroom_number || dev.classroomNumber || dev.ClassroomNumber || dev.Classrooms_ClassroomNumber || dev.classrooms_classroomNumber || dev.room || '',
      status: (dev.status !== undefined ? dev.status : dev.Status) ?? false
    })).filter(d => !!d.deviceId);
    if (activeSensorIndex >= sensors.length) activeSensorIndex = sensors.length ? 0 : -1;
    console.log('✅ Geräte geladen:', devices);
    console.log('ℹ️ Lokale Sensor-Objekte:', sensors);
    renderSensorTabs();
  renderOfflineSensors();
    refreshTabLabels();
    updateActiveSensorLabels();
  adjustSidebarWidth();
  if(window.updateHistorySensorOptions) window.updateHistorySensorOptions();
    updateValues();
    updateCharts();
    if(window.updateComparisonCharts) window.updateComparisonCharts();
  } catch (err) {
    console.warn('⚠️ Geräteabruf fehlgeschlagen:', err);
  }
}

// global verfügbar machen für externe Skripte (index.html Modal)
/**
 * Expose device refresh on the global window for other scripts/UI.
 * @global
 */
window.fetchDevices = fetchDevices;


// ---------------------------------------------------------------
// 2️⃣ Messwerte pro Sensor vom Backend abrufen
// ---------------------------------------------------------------
/**
 * Poll latest measurements for each known online sensor and update their rolling buffers.
 * Triggers UI updates for tiles and charts after fetching.
 * @returns {Promise<void>}
 */
async function fetchLatestMeasurements() {
  try {
    for (const s of sensors) {
      if (!s.deviceId) continue; // nur für bekannte IDs
      const res = await fetch(`${baseUrl}/sensor/getCurrentData/${s.deviceId}`);
      if (!res.ok) throw new Error("HTTP " + res.status);
      const payload = await res.json();
      // Backend kann entweder direkt die Messwerte liefern oder {success,data:{...}}
      const m = (payload && typeof payload === 'object') ? (payload.data || payload) : null;
      if(!m) continue;
      s.addMeasurement(m);
      // Debug optional
      // console.debug('Neue Messung', s.deviceName, m);
    }

    updateValues();
    updateCharts();
    if (window.updateComparisonCharts) window.updateComparisonCharts();
  } catch (err) {
    console.error("Messwerte Fehler:", err);
  }
}

// ---------------------------------------------------------------
// 3️⃣ Anzeige aktualisieren
// ---------------------------------------------------------------
/**
 * Update the metric tiles for the currently active sensor.
 * Applies simple grading classes based on thresholds for visual cues.
 * @returns {void}
 */
function updateValues() {
  const s = getActive();
  if (!s) return;

  const latestTemp = getActive()?.tempData?.at(-1);
  const latestCO2 = s.co2Data?.at(-1);

  if (latestTemp == null || latestCO2 == null) {
    console.warn("⚠️ Keine Sensordaten vorhanden für", s.deviceName);
    return;
  }

  const setVal = (el, value, unit, clsProvider) => {
    if (!el) return;
    el.textContent = value + (unit ? " " + unit : "");
    if (clsProvider) {
      const { level } = clsProvider(value);
      el.parentElement.classList.remove("metric-ok", "metric-mid", "metric-high");
      if (level) el.parentElement.classList.add(level);
    }
  };

  const grade = (value, thresholds) => {
    const { mid, high, reverse } = thresholds;
    let level = "metric-ok";
    if (!reverse) {
      if (value >= high) level = "metric-high";
      else if (value >= mid) level = "metric-mid";
    } else {
      if (value <= high) level = "metric-high";
      else if (value <= mid) level = "metric-mid";
    }
    return { level };
  };

  setVal(tempEl, latestTemp.toFixed(1), "°C", (v) => grade(v, { mid: 26, high: 30 }));
  setVal(humEl, s.humidity, "%", (v) => grade(v, { mid: 60, high: 70 }));
  setVal(co2El, latestCO2, "ppm", (v) => grade(v, { mid: 1000, high: 1400 }));
  setVal(pm25El, s.pm25, "µg/m³", (v) => grade(v, { mid: 25, high: 50 }));
  setVal(pm10El, s.pm10, "µg/m³", (v) => grade(v, { mid: 40, high: 80 }));
  setVal(tvocEl, s.tvoc, "ppm", (v) => grade(v, { mid: 0.5, high: 1 }));
  setVal(aqiEl, s.aqi, "", (v) => grade(v, { mid: 75, high: 125 }));
  setVal(coEl, s.co?.toFixed(2), "ppm", (v) => grade(v, { mid: 1.0, high: 2.0 }));
  setVal(hchoEl, s.hcho?.toFixed(3), "ppm", (v) => grade(v, { mid: 0.08, high: 0.12 }));
  setVal(pm03El, s.pm03, "µg/m³", (v) => grade(v, { mid: 40, high: 80 }));
  setVal(pm1El, s.pm1, "µg/m³", (v) => grade(v, { mid: 15, high: 30 }));
}

// ---------------------------------------------------------------
// 4️⃣ Charts – alle Messgrößen
// ---------------------------------------------------------------
/**
 * Chart definitions describing which sensor series are rendered and their display attributes.
 * @type {Array<{id:string,label:string,key:string,metric:string,color:string}>}
 */
const chartDefs = [
  { id:'chartTemperature', label:'Temperatur (°C)', key:'tempData', metric:'temp', color:'#ff5722' },
  { id:'chartCO2',         label:'CO₂ (ppm)',      key:'co2Data',  metric:'co2', color:'#2196f3' },
  { id:'chartHumidity',    label:'Luftfeuchte (%)',key:'humidityData', metric:'humidity', color:'#00acc1' },
  { id:'chartPM25',        label:'PM2.5 (µg/m³)',  key:'pm25Data', metric:'pm25', color:'#7b1fa2' },
  { id:'chartPM10',        label:'PM10 (µg/m³)',   key:'pm10Data', metric:'pm10', color:'#6a1b9a' },
  { id:'chartPM03',        label:'PM0.3 (µg/m³)',  key:'pm03Data', metric:'pm03', color:'#8e24aa' },
  { id:'chartPM1',         label:'PM1 (µg/m³)',    key:'pm1Data',  metric:'pm1', color:'#ab47bc' },
  { id:'chartTVOC',        label:'TVOC (ppb)',     key:'tvocData', metric:'tvoc', color:'#00796b' },
  { id:'chartCO',          label:'CO (ppm)',       key:'coData',   metric:'co', color:'#5d4037' },
  { id:'chartHCHO',        label:'HCHO (ppm)',     key:'hchoData', metric:'hcho', color:'#c62828' },
];
/**
 * Lookup of Chart.js instances keyed by DOM element id.
 * @type {Object<string, import('chart.js').Chart>}
 */
const charts = {};

/**
 * Adjust the Y-axis bounds dynamically based on current data and metric semantics.
 * @param {import('chart.js').Chart} chart Chart instance to tune.
 * @param {string} metric Metric identifier (e.g., 'tvoc', 'hcho', 'co2', ...).
 * @param {number[]} data Data points currently displayed.
 * @returns {void}
 */
function updateYAxisForMetric(chart, metric, data) {
  if(!chart || !chart.options.scales || !chart.options.scales.y) return;
  
  const validData = data.filter(v => v != null && !isNaN(v));
  if(validData.length === 0) return;
  
  const min = Math.min(...validData);
  const max = Math.max(...validData);
  
  if(metric === 'tvoc') {
    // TVOC: Dynamische Skalierung für kleine Werte
    const range = max - min;
    const padding = Math.max(0.002, range * 0.05);
    chart.options.scales.y.suggestedMin = Math.max(0, min - padding);
    chart.options.scales.y.suggestedMax = max + padding;
  } else if(metric === 'hcho') {
    // HCHO: Sehr feine Skalierung für sehr kleine Werte
    const range = max - min;
    const padding = Math.max(0.001, range * 0.05);
    chart.options.scales.y.suggestedMin = Math.max(0, min - padding);
    chart.options.scales.y.suggestedMax = max + padding;
  } else {
    const range = max - min;
    const padding = Math.max(1, range * 0.2); // add 1 unit or 20%
    chart.options.scales.y.suggestedMin = Math.max(0, min - padding);
    chart.options.scales.y.suggestedMax = max + padding;
  }
}

/**
 * Create a Chart.js line chart for a single metric.
 * @param {HTMLCanvasElement} ctx Canvas element.
 * @param {string} label Dataset label.
 * @param {string} color Hex color for line/background.
 * @param {string[]} labels X-axis labels (time).
 * @param {number[]} data Series data values.
 * @param {string} metric Metric identifier for axis tuning.
 * @returns {import('chart.js').Chart}
 */
function buildChart(ctx, label, color, labels, data, metric){
  const options = {
    responsive: true,
    animation: { duration: 250 },
    scales: {
      x: {
        display: true,
        ticks: {
          maxRotation: 0,
          autoSkip: true,
          maxTicksLimit: 8
        }
      },
      y: {
        beginAtZero: false
      }
    }
  };
  
  // Spezielle Y-Achsen-Konfiguration für verschiedene Metriken
  if(metric === 'tvoc') {
    // TVOC: Höhere Empfindlichkeit für kleine Werte
    options.scales.y = {
      beginAtZero: true,
      suggestedMin: 0,
      suggestedMax: Math.max(0.05, Math.max(...(data || [0])) * 1.1),
      ticks: {
        stepSize: 4
      }
    };
  } else if(metric === 'hcho') {
    // HCHO: Sehr hohe Empfindlichkeit für sehr kleine Werte
    options.scales.y = {
      beginAtZero: true,
      suggestedMin: 0,
      suggestedMax: Math.max(0.02, Math.max(...(data || [0])) * 1.1),
      ticks: {
        stepSize: 4,
        callback: function(value) {
          return value.toFixed(3);
        }
      }
    };
  } else {
    const maxVal = Math.max(...(data || [0]));
    const minVal = Math.min(...(data || [0]));
    const range = maxVal - minVal;
    const padding = Math.max(1, range * 0.2); // wider axis (20% padding or at least ±1)
    options.scales.y = {
      beginAtZero: false,
      suggestedMin: Math.max(0, minVal - padding),
      suggestedMax: maxVal + padding
    };
  }
  
  return new Chart(ctx, {
    type:'line',
    data:{ labels: labels || [], datasets:[{ label, data: data || [], borderColor: color, backgroundColor: color+'33', fill:true, tension:.3, pointRadius:2, spanGaps: true, borderJoinStyle:'round', borderCapStyle:'round' }] },
    options: options
  });
}
function initCharts(){
  if(!sensors.length) return;
  const active = getActive();
  if(!active) return;
  chartDefs.forEach(def=>{
    const el = document.getElementById(def.id);
    if(el && !charts[def.id]){
      charts[def.id] = buildChart(el, def.label, def.color, active.timeLabels, active[def.key], def.metric);
    }
  });
}
/**
 * Update all live or historical per-sensor charts based on the selected range.
 * Uses live rolling buffers for 'now' and fetches aggregated history for 'hour'/'day'.
 * @returns {Promise<void>|void}
 */
async function updateCharts(){
  if(Object.keys(charts).length === 0) initCharts();
  const s = getActive();
  if(!s) return;
  
  const chartRangeEl = document.getElementById('chartRange');
  const range = chartRangeEl ? chartRangeEl.value : 'now';
  
  if(range === 'now'){
    // Use live data from sensor objects
    chartDefs.forEach(def=>{
      const ch = charts[def.id];
      if(!ch) return;
      ch.data.labels = s.timeLabels || [];
      const data = s[def.key] || [];
      ch.data.datasets[0].data = data;
      
      // Dynamische Y-Achsen-Anpassung basierend auf aktuellen Daten
      updateYAxisForMetric(ch, def.metric, data);
      
      ch.update();
    });
  } else {
    // Fetch historical data for each chart
    await Promise.all(chartDefs.map(async (def) => {
      const ch = charts[def.id];
      if(!ch) return;
      
      let data = [];
      if(range === 'hour'){
        data = await cmpFetchHour(s, def.metric);
      } else if(range === 'day'){
        data = await cmpFetchDay(s, def.metric);
      }
      
  const labels = data.map((p, idx, list) => range === 'hour' ? cmpFmtHour(p.ts) : cmpFmtDayLabel(p, idx, list.length));
      const values = data.map(p => p.avg == null ? null : p.avg);
      
      ch.data.labels = labels;
      ch.data.datasets[0].data = values;
      
      // Dynamische Y-Achsen-Anpassung für historische Daten
      updateYAxisForMetric(ch, def.metric, values);
      
      ch.update();
    }));
  }
}

function refreshTabLabels(){
  const items = document.querySelectorAll('#sensorTabs .sensor-tab');
  items.forEach(li => {
    const idx = parseInt(li.dataset.sensor,10);
    const s = sensors[idx];
    if(!s) return;
    const span = li.querySelector('.sensor-tab-label');
    if(span){
      const room = s.classroomNumber ? ` - ${s.classroomNumber}` : '';
      span.textContent = `${s.deviceName || ('Sensor '+(idx+1))}${room}`;
    }
  });
  // Adjust sidebar width to longest label after labels refreshed
  adjustSidebarWidth();
}

// ---------------------------------------------------------------
// Historie: Sensor-Dropdown dynamisch mit aktiven Sensoren füllen
// ---------------------------------------------------------------
/**
 * Rebuild the history view sensor selector from the current online sensors list.
 * Tries to preserve the previous selection and triggers a reload if the history
 * section is visible.
 * @returns {void}
 */
function updateHistorySensorOptions(){
  const sel = document.getElementById('historySensor');
  if(!sel) return;
  const prev = sel.value;
  sel.innerHTML = '';
  sensors.forEach((s, i) => {
    const opt = document.createElement('option');
    opt.value = String(i); // Index als Referenz
    const room = s.classroomNumber ? ` - ${s.classroomNumber}` : '';
    opt.textContent = `${s.deviceName || ('Sensor '+(i+1))}${room}`;
    sel.appendChild(opt);
  });
  // Auswahl möglichst beibehalten
  if(prev && [...sel.options].some(o=>o.value===prev)){
    sel.value = prev;
  }
  // Falls eine History-Ladefunktion existiert, neu laden
  if(typeof window.loadHistory === 'function'){
    const sectionHistory = document.getElementById('section-history');
    const visible = sectionHistory && sectionHistory.style.display !== 'none';
    if (visible) {
      window.loadHistory();
    }
  }
}
window.updateHistorySensorOptions = updateHistorySensorOptions;

// Dynamically size sidebar to the longest sensor tab width
/**
 * Compute and apply a sidebar width that fits the longest sensor tab label
 * (including offline sensors list) to avoid truncation.
 * @returns {void}
 */
function adjustSidebarWidth(){
  try{
    const sidebar = document.querySelector('.sidebar');
    const tabs = document.querySelectorAll('#sensorTabs .sensor-tab, #offlineSensorsList .sensor-tab');
    if(!sidebar || tabs.length===0) return;
    // Allow natural sizing for measurement
    const prev = sidebar.style.width;
    sidebar.style.width = 'auto';
    let max = 0;
    tabs.forEach(tab => {
      const w = tab.scrollWidth; // natural width inc. icons
      if(w > max) max = w;
    });
    // Account for sidebar horizontal padding
    const cs = getComputedStyle(sidebar);
    const padLeft = parseFloat(cs.paddingLeft)||0;
    const padRight = parseFloat(cs.paddingRight)||0;
    const borderLeft = parseFloat(cs.borderLeftWidth)||0;
    const borderRight = parseFloat(cs.borderRightWidth)||0;
    const target = Math.ceil(max + padLeft + padRight + borderLeft + borderRight);
    sidebar.style.width = target + 'px';
  }catch(e){ /* noop */ }
}
// Simple debounce for resize handling
/**
 * Debounce helper to throttle high-frequency events like resize.
 * @template T
 * @param {function(...any): any} fn Function to debounce.
 * @param {number} wait Delay in milliseconds.
 * @returns {function(this:T, ...any): void}
 */
function debounce(fn, wait){ let t; return function(){ clearTimeout(t); t=setTimeout(()=>fn.apply(this, arguments), wait); }; }
window.addEventListener('resize', debounce(adjustSidebarWidth, 150));

// ---------------------------------------------------------------
// Suche in der Sensorspalte (nach Name oder Raum)
// ---------------------------------------------------------------
/**
 * Find the first sensor index by search query matching name or classroom number.
 * @param {string} q Query string.
 * @returns {number} Index in sensors array or -1 if not found.
 */
function findSensorIndexByQuery(q){
  if(!q) return -1;
  const needle = q.toString().trim().toLowerCase();
  if(!needle) return -1;
  // Zuerst exakte Starts-matches, dann enthält-Matches
  let idx = sensors.findIndex(s => (s.deviceName||'').toLowerCase().startsWith(needle) || (s.classroomNumber||'').toLowerCase().startsWith(needle));
  if(idx !== -1) return idx;
  idx = sensors.findIndex(s => (s.deviceName||'').toLowerCase().includes(needle) || (s.classroomNumber||'').toLowerCase().includes(needle));
  return idx;
}
/**
 * Activate a sensor by index and refresh tiles/charts.
 * @param {number} idx Index in the sensors array.
 * @returns {boolean} True if activated.
 */
function activateSensorByIndex(idx){
  if(idx < 0 || idx >= sensors.length) return false;
  const tab = document.querySelector(`#sensorTabs .sensor-tab[data-sensor="${idx}"]`);
  if(tab){ tab.click(); return true; }
  // fallback ohne DOM-Click
  activeSensorIndex = idx; updateValues(); updateCharts();
  return true;
}
// Event-Bindings für Suche
const sensorSearch = document.getElementById('sensorSearch');
if(sensorSearch){
  // Enter = ersten Treffer auswählen
  sensorSearch.addEventListener('keydown', (e)=>{
    if(e.key === 'Enter'){
      e.preventDefault();
      const idx = findSensorIndexByQuery(sensorSearch.value);
      if(idx !== -1) activateSensorByIndex(idx);
    } else if(e.key === 'Escape'){
      sensorSearch.value = '';
    }
  });
  // Live: Tabs dezent hervorheben (optional)
  sensorSearch.addEventListener('input', ()=>{
    const q = sensorSearch.value.toLowerCase().trim();
    document.querySelectorAll('#sensorTabs .sensor-tab').forEach((li)=>{
      const i = parseInt(li.dataset.sensor,10);
      const s = sensors[i];
      const match = q && s && (((s.deviceName||'').toLowerCase().includes(q)) || ((s.classroomNumber||'').toLowerCase().includes(q)));
      li.style.outline = match ? '2px solid var(--accent, #4caf50)' : '';
      li.style.backgroundColor = match ? 'var(--bg-match, rgba(76,175,80,0.08))' : '';
    });
  });
}

// ---------------------------------------------------------------
//  Vergleichs-Charts (Mehrere Sensoren / ausgewählte Messgröße)
// ---------------------------------------------------------------
let comparisonCharts = [];
const CMP_TZ = 'Europe/Vienna';
/**
 * Map UI metric names to backend API metric parameter names.
 * @param {string} metric UI metric (e.g., 'pm1', 'pm03').
 * @returns {string}
 */
function cmpMapMetricToApi(metric){
  const m = (metric||'').toLowerCase();
  if(m==='humidity') return 'hum';
  if(m==='pm25') return 'pm2_5';
  if(m==='pm03' || m==='pm3') return 'pm0_3';
  // history endpoints expect pm1 as pm1_0 (per current backend)
  if(m==='pm1') return 'pm1_0';
  return m;
}
function cmpFmtHour(ts){ try { const d=new Date(ts); return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit', timeZone:CMP_TZ}); } catch { return ts; } }
/**
 * Format a day-range label. Some APIs return {ts}, others an {hour} (0..23).
 * @param {{ts?:string|number, hour?:number}} point
 * @returns {string}
 */
function cmpFmtDayLabel(point, idx, total){
  try{
    if(point && (point.ts!==undefined && point.ts!==null)){
      return cmpFmtHour(point.ts);
    }
    // If only an hour is provided (0..23), derive rolling 24h labels anchored to now
    // using the index within the returned series: idx=0 oldest, idx=total-1 newest (now)
    const safeTotal = typeof total === 'number' && total > 0 ? total : 24;
    const safeIdx = typeof idx === 'number' ? idx : 0;
    const hoursFromNow = Math.max(0, (safeTotal - 1) - safeIdx);
    const d = new Date(Date.now() - hoursFromNow * 3600_000);
    return d.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit', timeZone:CMP_TZ});
  }catch{}
  return '';
}
/**
 * Fetch last hour aggregated history for a sensor/metric.
 * @param {Sensor} sensor Sensor instance.
 * @param {string} metric UI metric name.
 * @returns {Promise<Array<{ts:string, avg:number|null}>>}
 */
async function cmpFetchHour(sensor, metric){
  const apiMetric = cmpMapMetricToApi(metric);
  const url = `${baseUrl}/sensor/history/hour/${encodeURIComponent(sensor.deviceId)}?metric=${encodeURIComponent(apiMetric)}`;
  try{ const res = await fetch(url); const body = await res.json(); if(!res.ok || body.success===false) return []; return Array.isArray(body.data)?body.data:[]; } catch { return []; }
}
/**
 * Fetch last day aggregated history for a sensor/metric.
 * @param {Sensor} sensor Sensor instance.
 * @param {string} metric UI metric name.
 * @returns {Promise<Array<{ts:string, avg:number|null}>>}
 */
async function cmpFetchDay(sensor, metric){
  const apiMetric = cmpMapMetricToApi(metric);
  const url = `${baseUrl}/sensor/history/day/${encodeURIComponent(sensor.deviceId)}?metric=${encodeURIComponent(apiMetric)}`;
  try{ const res = await fetch(url); const body = await res.json(); if(!res.ok || body.success===false) return []; return Array.isArray(body.data)?body.data:[]; } catch { return []; }
}
/**
 * Return the rolling series for a given metric from a sensor.
 * @param {Sensor} sensor
 * @param {string} metric
 * @returns {number[]}
 */
function getSeriesForMetric(sensor, metric){
  switch(metric){
    case 'temp': return sensor.tempData;
    case 'co2': return sensor.co2Data;
    case 'humidity': return sensor.humidityData;
    case 'pm25': return sensor.pm25Data;
    case 'pm10': return sensor.pm10Data;
    case 'pm03': return sensor.pm03Data;
    case 'pm3': return sensor.pm03Data; // alias for UI consistency
    case 'pm1': return sensor.pm1Data;
    case 'tvoc': return sensor.tvocData;
    case 'co': return sensor.coData;
    case 'hcho': return sensor.hchoData;
    default: return [];
  }
}
/**
 * Return a stable color per metric for chart series.
 * @param {string} metric
 * @returns {string}
 */
function colorForMetric(metric){
  const map={
    temp:'#ff7043', co2:'#1976d2', humidity:'#0288d1', pm25:'#7b1fa2', pm10:'#6a1b9a', pm03:'#8e24aa', pm3:'#8e24aa', pm1:'#ab47bc', tvoc:'#00796b', co:'#5d4037', hcho:'#c62828'
  }; return map[metric]||'#607d8b';
}
/**
 * Initialize comparison charts grid and create per-sensor chart instances.
 * @returns {void}
 */
function initComparisonCharts(){
  const metricSel = document.getElementById('comparisonMetric');
  const metric = metricSel ? metricSel.value : 'temp';
  const grid = document.querySelector('.comparison-grid');
  if(grid){
    // Falls eigene dynamische Erzeugung nötig (wenn keine canvases vorhanden)
    const existing = grid.querySelectorAll('.comp-chart-item');
    if(existing.length < sensors.length){
      for(let i=existing.length;i<sensors.length;i++){
        const div = document.createElement('div');
        div.className = 'comp-chart-item';
        const canvas = document.createElement('canvas');
        canvas.id = `compSensor${i}`;
        const p = document.createElement('p');
        p.className = 'comp-label';
        const s = sensors[i];
        const name = s && s.deviceName ? s.deviceName : `Sensor ${i+1}`;
        const room = s && s.classroomNumber ? ` - ${s.classroomNumber}` : '';
        p.textContent = `${name}${room}`;
        div.appendChild(canvas);
        div.appendChild(p);
        grid.appendChild(div);
      }
    }
    // Überzählige verstecken
    grid.querySelectorAll('.comp-chart-item').forEach((el,i)=>{
      el.style.display = i < sensors.length ? '' : 'none';
    });
    // Bereits vorhandene Labels an echte Namen anpassen
    grid.querySelectorAll('.comp-chart-item .comp-label').forEach((labelEl, i)=>{
      if(!sensors[i]) return;
      const s = sensors[i];
      const name = s.deviceName || `Sensor ${i+1}`;
      const room = s.classroomNumber ? ` - ${s.classroomNumber}` : '';
      labelEl.textContent = `${name}${room}`;
    });
  }
  comparisonCharts = comparisonCharts || [];
  for(let i=0;i<sensors.length;i++){
    const canvas = document.getElementById(`compSensor${i}`);
    if(!canvas) continue;
    if(!comparisonCharts[i]){
      const col = colorForMetric(metric);
      const labels = sensors[i].timeLabels.slice(-WINDOW_SIZE);
      const data = getSeriesForMetric(sensors[i], metric).slice(-WINDOW_SIZE);
      const chartOptions = {
        responsive:true,
        animation:{ duration:200 },
        plugins:{ legend:{ display:false } },
        scales:{
          x:{ display:true, ticks:{ maxRotation:0, autoSkip:false, maxTicksLimit:5 } },
          y:{ display:true, ticks:{ maxTicksLimit:4 } }
        }
      };
      
      // Spezielle Y-Achsen-Konfiguration für Vergleichscharts
      if(metric === 'tvoc') {
        chartOptions.scales.y.beginAtZero = true;
        chartOptions.scales.y.suggestedMax = Math.max(10, Math.max(...data) * 1.2);
      } else if(metric === 'hcho') {
        chartOptions.scales.y.beginAtZero = true;
        chartOptions.scales.y.suggestedMax = Math.max(0.1, Math.max(...data) * 1.5);
        chartOptions.scales.y.ticks.callback = function(value) {
          return value.toFixed(3);
        };
      }
      
      comparisonCharts[i] = new Chart(canvas, {
        type:'line',
        data:{ labels, datasets:[{ label:`${sensors[i].deviceName}`, data, borderColor:col, backgroundColor:col+'33', tension:.25, spanGaps: true, fill:true, pointRadius:2 }]},
        options: chartOptions
      });
    }
  }
  updateComparisonCharts();
}


/**
 * Update comparison charts for the selected metric and time range ('now' | 'hour' | 'day').
 * @returns {Promise<void>|void}
 */
async function updateComparisonCharts(){
  const metricSel = document.getElementById('comparisonMetric');
  const metric = metricSel ? metricSel.value : 'temp';
  const rangeSel = document.getElementById('comparisonRange');
  const range = rangeSel ? rangeSel.value : 'now'; // now|hour|day
  const col = colorForMetric(metric);
  // Labels in der Grid-UI an echte Namen/Raum angleichen (bei 'Aktuell' zusätzlich Uhrzeit)
  const grid = document.querySelector('.comparison-grid');
  if(grid){
    grid.querySelectorAll('.comp-chart-item .comp-label').forEach((labelEl, i)=>{
      const s = sensors[i];
      if(!s) return;
      const name = s.deviceName || `Sensor ${i+1}`;
      const room = s.classroomNumber ? ` - ${s.classroomNumber}` : '';
      if(range === 'now'){
        const lastLabel = (s.timeLabels && s.timeLabels.length) ? s.timeLabels.at(-1) : '';
        labelEl.textContent = `${name}${room}${lastLabel ? ' um '+lastLabel : ''}`;
      } else {
        labelEl.textContent = `${name}${room}`;
      }
    });
  }
  if(range === 'now'){
    comparisonCharts.forEach((ch,i)=>{
      if(!ch || !sensors[i]) return;
      const s = sensors[i];
      const series = getSeriesForMetric(s, metric);
      const data = (series || []).slice();
      // Use the same rolling WINDOW_SIZE data as in Verlaufsmessungen
      ch.data.labels = (s.timeLabels || []).slice();
      ch.data.datasets[0].data = data;
      ch.data.datasets[0].borderColor = col;
      ch.data.datasets[0].backgroundColor = col+'33';
      ch.data.datasets[0].label = sensors[i].deviceName;
      
      // Dynamische Y-Achsen-Anpassung auch für Vergleichscharts
      updateYAxisForMetric(ch, metric, data);
      
      // Reset tick behavior for live view
      if(!ch.options.scales) ch.options.scales = {};
      if(!ch.options.scales.x) ch.options.scales.x = {};
      if(!ch.options.scales.x.ticks) ch.options.scales.x.ticks = {};
      ch.options.scales.x.ticks.autoSkip = true;
      ch.options.scales.x.ticks.maxTicksLimit = Math.max(3, Math.min(7, ch.data.labels.length || 5));
      ch.options.scales.x.ticks.callback = undefined;
      ch.update();
    });
    return;
  }
  if(range === 'hour'){
    const all = await Promise.all(sensors.map(s=>cmpFetchHour(s, metric)));
    all.forEach((arr,i)=>{
      const ch = comparisonCharts[i]; if(!ch) return;
      const labels = arr.map(p=>cmpFmtHour(p.ts));
      const values = arr.map(p=> p.avg==null?null:p.avg);
      ch.data.labels = labels;
      ch.data.datasets[0].data = values;
      ch.data.datasets[0].borderColor = col;
      ch.data.datasets[0].backgroundColor = col+'33';
      ch.data.datasets[0].label = sensors[i].deviceName;
      
      // Dynamische Y-Achsen-Anpassung für historische Daten
      updateYAxisForMetric(ch, metric, values);
      
      // Only show a tick label every 10 minutes on the x-axis
      if(!ch.options.scales) ch.options.scales = {};
      if(!ch.options.scales.x) ch.options.scales.x = {};
      if(!ch.options.scales.x.ticks) ch.options.scales.x.ticks = {};
      ch.options.scales.x.ticks.autoSkip = false;
      ch.options.scales.x.ticks.maxTicksLimit = labels.length || 60;
      ch.options.scales.x.ticks.callback = (value, idx) => {
        const lbl = ch.data.labels && ch.data.labels[idx];
        if(!lbl) return '';
        const parts = String(lbl).split(':');
        if(parts.length < 2) return lbl;
        const min = parseInt(parts[1],10);
        return (!isNaN(min) && (min % 10 === 0)) ? lbl : '';
      };
      ch.update();
    });
    return;
  }
  if(range === 'day'){
    const all = await Promise.all(sensors.map(s=>cmpFetchDay(s, metric)));
    all.forEach((arr,i)=>{
      const ch = comparisonCharts[i]; if(!ch) return;
  const labels = arr.map((p, idx, list)=>cmpFmtDayLabel(p, idx, list.length));
      const values = arr.map(p=> p.avg==null?null:p.avg);
      ch.data.labels = labels;
      ch.data.datasets[0].data = values;
      ch.data.datasets[0].borderColor = col;
      ch.data.datasets[0].backgroundColor = col+'33';
      ch.data.datasets[0].label = sensors[i].deviceName;
      
      // Dynamische Y-Achsen-Anpassung für Tages-Daten
      updateYAxisForMetric(ch, metric, values);
      
      // Reset tick behavior for non-hour ranges
      if(!ch.options.scales) ch.options.scales = {};
      if(!ch.options.scales.x) ch.options.scales.x = {};
      if(!ch.options.scales.x.ticks) ch.options.scales.x.ticks = {};
      ch.options.scales.x.ticks.autoSkip = true;
      ch.options.scales.x.ticks.maxTicksLimit = 12;
      ch.options.scales.x.ticks.callback = undefined;
      ch.update();
    });
    return;
  }
}
window.initComparisonCharts = initComparisonCharts;
window.updateComparisonCharts = updateComparisonCharts;
document.addEventListener('change',(e)=>{
  if(e.target && e.target.id==='comparisonMetric'){
    // Reset Charts to adapt color/label
    updateComparisonCharts();
  }
  if(e.target && e.target.id==='comparisonRange'){
    // Zeitraum gewechselt – aktuell keine Aggregation, aber Update triggert Re-Render
    updateComparisonCharts();
  }
  if(e.target && e.target.id==='chartRange'){
    // Zeitraum für Verlaufsmessungen gewechselt
    updateCharts();
  }
});

// ---------------------------------------------------------------
// 5️⃣ Tabs Umschalten
// ---------------------------------------------------------------
const tabsContainer = document.getElementById("sensorTabs");
if (tabsContainer) {
  tabsContainer.addEventListener("click", (e) => {
    const tab = e.target.closest(".sensor-tab");
    if (!tab) return;
    const idx = parseInt(tab.dataset.sensor, 10);
  if (idx < 0 || idx >= sensors.length) return;
    activeSensorIndex = idx;

    updateValues();
    updateCharts();
    updateActiveSensorLabels();
    tabsContainer
      .querySelectorAll(".sensor-tab")
      .forEach((li) => li.classList.toggle("active", li === tab));
  });
}

// ---------------------------------------------------------------
// 6️⃣ Simulation (nur falls Backend keine Daten liefert)
// ---------------------------------------------------------------
// Simulation deaktiviert – falls nötig zum Testen einkommentieren
// setInterval(() => { /* MOCK FALLBACK */ }, 5000);

// ---------------------------------------------------------------
// 7️⃣ Initialisierung
// ---------------------------------------------------------------

/**
 * Render the online sensors as tabs (and admin action buttons when in Current view).
 * @returns {void}
 */
function renderSensorTabs(){
      const ul = document.getElementById('sensorTabs'); if(!ul) return;
      const list = sensors; ul.innerHTML='';
      const isCurrent = (()=>{
        const activeBtn = document.querySelector('.view-tab.active');
        return activeBtn ? (activeBtn.dataset.view === 'current') : true;
      })();
      const admin = __isAdmin();
      list.forEach((s,idx)=>{
        const li=document.createElement('li');
        li.className='sensor-tab'+(idx===0?' active':'');
        li.dataset.sensor=idx;
        let html = `<span class="sensor-tab-label">${s.deviceName} - ${s.classroomNumber}</span>`;
        if(isCurrent && admin){
          html += `
          <button type="button" class="edit-sensor-btn" data-index="${idx}" aria-label="Sensor bearbeiten" title="Sensor bearbeiten">✏️</button>
          <button type="button" class="delete-sensor-btn" data-index="${idx}" aria-label="Sensor löschen" title="Sensor löschen">🗑️</button>`;
        }
        li.innerHTML = html;
        ul.appendChild(li);
      });
      // After tabs are rendered, ensure sidebar width matches longest
      adjustSidebarWidth();
      // Toggle add button visibility based on role
      const addBtn = document.getElementById('openAddSensor');
      if(addBtn){ addBtn.style.display = admin ? '' : 'none'; }
    }

// Render offline sensors dropdown under the online list
/**
 * Render the offline sensors collapsible section below the online list.
 * @returns {void}
 */
function renderOfflineSensors(){
  const sidebar = document.querySelector('.sidebar');
  if(!sidebar) return;
  let section = document.getElementById('offlineSensorsSection');
  if(!section){
    section = document.createElement('details');
    section.id = 'offlineSensorsSection';
    section.className = 'offline-section';
    const summary = document.createElement('summary');
    summary.id = 'offlineSensorsSummary';
    summary.textContent = 'Offline Sensoren';
    const ul = document.createElement('ul');
    ul.id = 'offlineSensorsList';
    ul.className = 'sensor-tabs';
    section.appendChild(summary);
    section.appendChild(ul);
    // Insert after online list
    const onlineUl = document.getElementById('sensorTabs');
    if(onlineUl && onlineUl.parentNode){
      onlineUl.parentNode.insertBefore(section, onlineUl.nextSibling);
    } else {
      sidebar.appendChild(section);
    }
  }
  const listEl = document.getElementById('offlineSensorsList');
  const summary = document.getElementById('offlineSensorsSummary');
  if(!listEl || !summary) return;
  // Fill list
  listEl.innerHTML='';
  if(!offlineSensors || offlineSensors.length===0){
    summary.textContent = 'Offline Sensoren (0)';
    return;
  }
  summary.textContent = `Offline Sensoren (${offlineSensors.length})`;
  offlineSensors.forEach((d, i)=>{
    const li = document.createElement('li');
    li.className = 'sensor-tab offline';
    li.setAttribute('role','button');
    li.tabIndex = 0;
    const label = `${d.name || 'Sensor'}${d.classroom ? ' - '+d.classroom : ''}`;
    const isAdmin = (__isAdmin && __isAdmin()) || false;
    li.innerHTML = `
      <span class=\"status-dot\" aria-hidden=\"true\"></span>
      <span class=\"sensor-tab-label\">${label}</span>
      <span class=\"badge-offline\">Offline</span>
      ${isAdmin ? `<button type=\"button\" class=\"delete-sensor-btn\" data-deviceid=\"${d.deviceId}\" title=\"Sensor löschen\">🗑</button>` : ''}`;
    // Tooltip mit Device ID
    li.title = `Sensor ist offline\nID: ${d.deviceId || ''}`;
    listEl.appendChild(li);
  });
  // Recompute width including offline list
  adjustSidebarWidth();
}
// (updateCharts ist weiter oben definiert)

// Debug-Zugriff
/** Return the in-memory sensors array (for debugging). */
window.__SENSORS__ = () => sensors;
/** Switch active sensor by index (for debugging). */
window.__switchSensor = (i) => {
  if(sensors[i]){ activeSensorIndex = i; updateValues(); updateCharts(); updateActiveSensorLabels(); }
};

// Re-render tabs when switching main views so action buttons only appear on 'Aktuelle Messwerte'
document.addEventListener('click', (e)=>{
  const vt = e.target.closest && e.target.closest('.view-tab');
  if(vt){
    // allow the main handler to toggle views first
    setTimeout(()=>{ renderSensorTabs(); }, 0);
  }
});

// Start-Sequenz: Geräte laden, erste Messwerte holen, dann Charts initialisieren
(async () => { 
  await fetchDevices();
  await fetchLatestMeasurements();
  initCharts();
  updateCharts();
  updateActiveSensorLabels();
  if(window.initComparisonCharts) window.initComparisonCharts();
  setInterval(async () => {
    await fetchLatestMeasurements();
    // Only update charts automatically if we're in 'now' mode
    const chartRangeEl = document.getElementById('chartRange');
    const range = chartRangeEl ? chartRangeEl.value : 'now';
    if(range === 'now'){
      updateCharts();
    }
  }, 5000);
})();
