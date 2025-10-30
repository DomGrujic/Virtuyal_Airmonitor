/**
 * \file charts-history.js
 * \brief History chart module for aggregated sensor data (day/week/month/year) including CSV/PDF export.
 *
 * \details Initializes and updates a Chart.js line chart for historical sensor data and exposes
 * utility functions on window for UI integration. Documented with JSDoc so Doxygen can include it
 * in the combined frontend+backend documentation.
 *
 * @module ChartsHistory
 */

// History Chart (day-only)
(() => {
  /**
   * Base URL of the backend API.
   * @type {string}
   */
  const baseUrl = (window.location && window.location.origin ? window.location.origin : '') + '/api';
  /**
   * Chart.js instance for the history view.
   * @type {import('chart.js').Chart|null}
   */
  let historyChart = null;
  /**
   * IANA timezone used for formatting labels (Europe/Vienna).
   * @type {string}
   */
  const TZ = 'Europe/Vienna';
  // cache last loaded series for CSV export
  /**
   * Last loaded history series points from API.
   * @type {Array<HistoryPoint>|null}
   */
  let lastHistorySeries = null; // array of { ts, avg, n }
  /**
   * Metadata of the last loaded series, used for exports and labels.
   * @type {HistoryMeta|null}
   */
  let lastHistoryMeta = null;   // { deviceId, sensorName, room, metric, range, unit, labels }

  /**
   * A single aggregated history sample.
   * @typedef {Object} HistoryPoint
   * @property {string} ts ISO timestamp of the bucket.
   * @property {number|null} avg Average value for the bucket (null if insufficient data).
   * @property {number} [n] Number of raw samples aggregated.
   */

  /**
   * Metadata of the current history context.
   * @typedef {Object} HistoryMeta
   * @property {string} deviceId Backend device id
   * @property {string} sensorName Display name
   * @property {string} [room] Classroom label
   * @property {string} metric Metric key as selected in UI
   * @property {('day'|'week'|'month'|'year')} range Selected range
   * @property {string} unit Unit string for display
   * @property {string[]} labels Chart axis labels
   */

  /**
   * Return human-friendly label and unit for a UI metric key.
   * @param {string} metric UI metric key
   * @returns {{label:string, unit:string}}
   */
  function metricMeta(metric) {
    const map = {
      temp: { label: 'Temperatur', unit: '°C' },
      co2: { label: 'CO₂', unit: 'ppm' },
      hum: { label: 'Luftfeuchte', unit: '%' },
      humidity: { label: 'Luftfeuchte', unit: '%' }, // UI alias
      pm25: { label: 'PM2.5', unit: 'µg/m³' },
      pm2_5: { label: 'PM2.5', unit: 'µg/m³' }, // API alias
      pm10: { label: 'PM10', unit: 'µg/m³' },
      pm03: { label: 'PM0.3', unit: 'µg/m³' },
      pm0_3: { label: 'PM0.3', unit: 'µg/m³' }, // API alias
      pm1: { label: 'PM1', unit: 'µg/m³' },
      pm1_0: { label: 'PM1', unit: 'µg/m³' }, // API alias (backend)
      tvoc: { label: 'TVOC', unit: 'ppm' },
      co: { label: 'CO', unit: 'ppm' },
      hcho: { label: 'HCHO', unit: 'ppm' },
    };
    return map[metric] || { label: metric, unit: '' };
  }

  // Map UI metric keys to backend API keys when sending
  /**
   * Map a UI metric key to the backend API parameter name.
   * @param {string} metric UI metric key (e.g., 'pm1', 'pm25', 'pm03')
   * @returns {string}
   */
  function mapMetricToApi(metric) {
    const m = (metric || '').toLowerCase();
    if (m === 'humidity') return 'hum';
    if (m === 'pm1') return 'pm1_0';
    if (m === 'pm25') return 'pm2_5';
    if (m === 'pm3' || m === 'pm03') return 'pm0_3';
    return m;
  }

  /**
   * Format timestamp to hour:minute in the configured timezone.
   * @param {string} ts ISO timestamp
   * @returns {string}
   */
  function fmtHour(ts) {
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: TZ });
    } catch { return ts; }
  }
  /**
   * Format timestamp to short weekday + hour:minute for week range.
   * @param {string} ts ISO timestamp
   * @returns {string}
   */
  function fmtWeekTs(ts){
    try{
      const d = new Date(ts);
      const day = d.toLocaleDateString('de-DE', { weekday: 'short', timeZone: TZ });
      const hm  = d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', timeZone: TZ });
      return `${day} ${hm}`;
    } catch { return ts; }
  }
  /**
   * Format timestamp to dd.MM. for month/year ranges.
   * @param {string} ts ISO timestamp
   * @returns {string}
   */
  function fmtDay(ts){
    try{
      const d = new Date(ts);
      // dd.MM.
      const day = d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', timeZone: TZ });
      return day;
    } catch { return ts; }
  }

  /**
   * Ensure a Chart.js instance exists for the history canvas and return it.
   * Lazily creates the chart if necessary.
   * @returns {import('chart.js').Chart|null}
   */
  function ensureChart() {
    const ctx = document.getElementById('historyChart');
    if (!ctx) return null;
    if (!historyChart) {
      historyChart = new Chart(ctx, {
        type: 'line',
        data: { labels: [], datasets: [{ label: 'Historie', data: [], borderColor: '#1976d2', backgroundColor: '#1976d233', fill: true, tension: .25, spanGaps: false, pointRadius: 2 }] },
        options: { responsive: true, animation: { duration: 200 }, scales: { x: { ticks: { maxRotation: 0, autoSkip: true, maxTicksLimit: 14 } }, y: { beginAtZero: true, min: 0, ticks: { maxTicksLimit: 6 } } } }
      });
    }
    return historyChart;
  }

  /**
   * Load historical data for the selected sensor/metric/range from the DOM selectors
   * and update the history chart accordingly. Also caches the latest series and meta
   * for export functions.
   * @returns {Promise<void>}
   */
  async function loadHistory() {
    const hint = document.getElementById('historyHint');
    const sensorSel = document.getElementById('historySensor');
    const metricSel = document.getElementById('historyMetric');
    const rangeSel = document.getElementById('historyRange');
    if (!sensorSel || !metricSel || !rangeSel) return;

    const range = (rangeSel.value || 'day');
    if (range !== 'day' && range !== 'week' && range !== 'month' && range !== 'year') {
      if (hint) { hint.textContent = 'Aktuell sind Tag, Woche, Monat und Jahr implementiert.'; hint.style.color = 'var(--color-text-soft,#666)'; }
    } else if (hint) { hint.textContent = ''; }

    const idx = parseInt(sensorSel.value, 10);
    if (isNaN(idx) || !window.__SENSORS__) return;
    const list = window.__SENSORS__();
    const s = list[idx];
    if (!s || !s.deviceId) { if (hint) hint.textContent = 'Kein Sensor ausgewählt.'; return; }

  const metric = metricSel.value || 'temp';
  const apiMetric = mapMetricToApi(metric);

  // Backend endpoints by range (day/week/month/year supported)
  const basePath = (range === 'week') ? 'week' : (range === 'month' ? 'month' : (range === 'year' ? 'year' : 'day'));
  const url = `${baseUrl}/sensor/history/${basePath}/${encodeURIComponent(s.deviceId)}?metric=${encodeURIComponent(apiMetric)}`;
    try {
      if (hint) { hint.textContent = 'Wird geladen...'; hint.style.color = ''; }
      const res = await fetch(url, { method: 'GET' });
      const body = await res.json();
      if (!res.ok || body.success === false) {
        if (hint) { hint.textContent = 'Fehler: ' + (body.error || res.status); hint.style.color = 'var(--color-danger,#c62828)'; }
        return;
      }
  const labels = (body.data || []).map(p => (range==='week' ? fmtWeekTs(p.ts) : ((range==='month'||range==='year') ? fmtDay(p.ts) : fmtHour(p.ts))));
      const values = (body.data || []).map(p => p.avg == null ? null : p.avg);
      const meta = metricMeta(metric);
      const ch = ensureChart();
      if (!ch) return;
      ch.data.labels = labels;
      ch.data.datasets[0].data = values;
      ch.data.datasets[0].label = `${meta.label}${meta.unit ? ' (' + meta.unit + ')' : ''}`;
      // Feinere y-Skalierung für HCHO damit die Linie nicht an 0 klebt
      if(!ch.options.scales) ch.options.scales = {};
      if(!ch.options.scales.y) ch.options.scales.y = {};
      if ((metric || '').toLowerCase() === 'hcho') {
        const nums = values.filter(v => v != null && isFinite(v));
        if (nums.length) {
          let min = Math.min(...nums);
          let max = Math.max(...nums);
          if (min === max) {
            if (min === 0) { max = 0.1; }
            else { const pad = Math.abs(min) * 0.2 || 0.02; min = Math.max(0, min - pad); max = max + pad; }
          } else {
            const range = max - min;
            const pad = range * 0.15 || 0.02;
            min = Math.max(0, min - pad);
            max = max + pad;
          }
          if (max < 0.1) max = 0.1;
          ch.options.scales.y.min = min;
          ch.options.scales.y.max = max;
        } else {
          ch.options.scales.y.min = undefined;
          ch.options.scales.y.max = undefined;
        }
      } else {
        // dynamic scaling for all other metrics
        const nums = values.filter(v => v != null && isFinite(v));
        if (nums.length) {
          let min = Math.min(...nums);
          let max = Math.max(...nums);
          const range = max - min;
          const pad = range * 0.15 || 0.5; // add breathing room
          min = Math.max(0, min - pad);
          max = max + pad;
          ch.options.scales.y.min = min;
          ch.options.scales.y.max = max;
        } else {
          ch.options.scales.y.min = undefined;
          ch.options.scales.y.max = undefined;
        }
      }
      ch.update();
      // cache for export
      const sensorName = s.deviceName || `Sensor ${idx+1}`;
      const room = s.classroomNumber || '';
      lastHistorySeries = body.data || [];
      lastHistoryMeta = { deviceId: s.deviceId, sensorName, room, metric, range, unit: meta.unit || '', labels };
      if (hint) { hint.textContent = body.message || ''; hint.style.color = 'var(--color-text-soft,#666)'; }
    } catch (err) {
      if (hint) { hint.textContent = 'Netzwerkfehler: ' + err; hint.style.color = 'var(--color-danger,#c62828)'; }
    }
  }

  /**
   * Export the last loaded history series to a CSV file using a semicolon separator (de-DE friendly).
   * Includes ISO timestamp, localized time, value, sample count, metric, unit, sensor and room.
   * @returns {void}
   */
  function exportHistoryCSV() {
    const hint = document.getElementById('historyHint');
    // Admin-only guard
    try {
      const isAdmin = (window.__IS_ADMIN__ && window.__IS_ADMIN__()) || false;
      if (!isAdmin) {
        if (hint) { hint.textContent = 'Nur Administratoren dürfen exportieren.'; hint.style.color = 'var(--color-text-soft,#666)'; }
        return;
      }
    } catch(e) { return; }
    if (!lastHistorySeries || !lastHistorySeries.length || !lastHistoryMeta) {
      if (hint) { hint.textContent = 'Keine Daten zum Exportieren.'; hint.style.color = 'var(--color-text-soft,#666)'; }
      return;
    }
    const { deviceId, sensorName, room, metric, range, unit } = lastHistoryMeta;
    const rows = [];
    // Deutsche Header mit klaren Bezeichnungen
    rows.push(['Zeitstempel (ISO)','Zeit (Lokal Wien)','Wert','Anzahl','Messgröße','Einheit','Sensor','Raum','Device ID','Zeitraum']);
    // Datensätze
    lastHistorySeries.forEach((p) => {
      const ts = p.ts || '';
      let local = '';
      try {
        const d = new Date(ts);
        local = d.toLocaleString('de-DE', { year:'numeric', month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit', timeZone: TZ });
      } catch {}
      const val = p.avg == null ? '' : p.avg;
      const n = p.n == null ? '' : p.n;
      rows.push([ts, local, val, n, metric, unit, sensorName, room, deviceId, range]);
    });
    // CSV mit Semikolon als Trennzeichen für bessere Lesbarkeit in de-DE
    const sep = ';';
    const csv = rows.map(r => r.map(field => {
      const s = String(field ?? '');
      if (s.includes('"') || s.includes(sep) || s.includes('\n')) {
        return '"' + s.replace(/"/g, '""') + '"';
      }
      return s;
    }).join(sep)).join('\n');
    const bom = '\ufeff';
    const blob = new Blob([bom + csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    const url = URL.createObjectURL(blob);
    const safeName = (sensorName || 'sensor').replace(/[^a-z0-9_-]+/gi, '_');
    const now = new Date();
    const stamp = now.toISOString().replace(/[:T]/g,'-').split('.')[0];
    a.href = url;
    a.download = `history_${safeName}_${metric}_${range}_${stamp}.csv`;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { document.body.removeChild(a); URL.revokeObjectURL(url); }, 0);
  }

  /**
   * Export the current history chart and metadata to a PDF document.
   * Requires jsPDF to be available on window.jspdf.
   * @returns {Promise<void>}
   */
  async function exportHistoryPDF() {
    const hint = document.getElementById('historyHint');
    // Admin-only guard
    try {
      const isAdmin = (window.__IS_ADMIN__ && window.__IS_ADMIN__()) || false;
      if (!isAdmin) {
        if (hint) { hint.textContent = 'Nur Administratoren dürfen exportieren.'; hint.style.color = 'var(--color-text-soft,#666)'; }
        return;
      }
    } catch(e) { return; }
    if (!lastHistorySeries || !lastHistorySeries.length || !lastHistoryMeta) {
      if (hint) { hint.textContent = 'Keine Daten zum Exportieren.'; hint.style.color = 'var(--color-text-soft,#666)'; }
      return;
    }
    try {
      const { jsPDF } = window.jspdf || window.jspdf || {};
      if (!jsPDF) {
        if (hint) { hint.textContent = 'PDF-Export-Bibliothek nicht geladen.'; hint.style.color = 'var(--color-danger,#c62828)'; }
        return;
      }
      const canvasEl = document.getElementById('historyChart');
      if (!canvasEl) {
        if (hint) { hint.textContent = 'Chart nicht gefunden.'; hint.style.color = 'var(--color-danger,#c62828)'; }
        return;
      }
      // Render current chart canvas to image
      const dataUrl = canvasEl.toDataURL('image/png', 1.0);
      const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
      const pageWidth = doc.internal.pageSize.getWidth();
      const pageHeight = doc.internal.pageSize.getHeight();

      // Header
      doc.setFont('helvetica', 'bold');
      doc.setFontSize(16);
      doc.text('Virtuyal – Historie Export', 40, 40);
      doc.setFontSize(10);
      const now = new Date();
      const stamp = now.toLocaleString('de-DE');
      doc.text(`Erstellt: ${stamp}`, pageWidth - 200, 40);

      // Metadata
  const { deviceId, sensorName, room, metric, range, unit } = lastHistoryMeta;
  const rangeDe = (r => ({ day:'Tag', week:'Woche', month:'Monat', year:'Jahr' }[r] || r))(range || 'day');
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(11);
      const metaLines = [
        `Sensor: ${sensorName || ''}${room ? ' – ' + room : ''}`,
        `Device ID: ${deviceId || ''}`,
        `Messgröße: ${metricMeta(metric).label}${unit ? ' ('+unit+')' : ''}`,
        `Zeitraum: ${rangeDe}`,
      ];
      let y = 65;
      metaLines.forEach(line => { doc.text(line, 40, y); y += 16; });

      // Image placement keeping margins
      const margin = 40;
      const maxW = pageWidth - margin * 2;
      const maxH = pageHeight - margin * 2 - 40; // leave header space
      // Estimate chart aspect ratio from canvas
      const imgW = canvasEl.width;
      const imgH = canvasEl.height;
      let w = maxW, h = (imgH / imgW) * w;
      if (h > maxH) { h = maxH; w = (imgW / imgH) * h; }
      const x = (pageWidth - w) / 2;
      const imgY = y + 8;
      doc.addImage(dataUrl, 'PNG', x, imgY, w, h, undefined, 'FAST');

      // Footer note
      doc.setFontSize(9);
      doc.setTextColor('#666666');
      doc.text('Datenquelle: Virtuyal API', margin, pageHeight - margin * 0.6);

      const safeName = (sensorName || 'sensor').replace(/[^a-z0-9_-]+/gi, '_');
      doc.save(`history_${safeName}_${metric}_${range}.pdf`);
      if (hint) { hint.textContent = 'PDF erfolgreich erstellt.'; hint.style.color = 'var(--color-text-soft,#666)'; }
    } catch (err) {
      if (hint) { hint.textContent = 'Fehler beim PDF-Export: ' + err; hint.style.color = 'var(--color-danger,#c62828)'; }
    }
  }

  /**
   * Initialize the history chart area: bind selectors and export buttons, and load initial data.
   * Expects the presence of DOM elements with ids: historySensor, historyMetric, historyRange,
   * historyRefresh, historyExport, historyExportPdf.
   * @returns {void}
   */
  function initHistoryChart() {
    // Sensorauswahl ggf. neu füllen
    if (window.updateHistorySensorOptions) window.updateHistorySensorOptions();
    // Listener
    const sensorSel = document.getElementById('historySensor');
    const metricSel = document.getElementById('historyMetric');
    const rangeSel = document.getElementById('historyRange');
    const refreshBtn = document.getElementById('historyRefresh');
    const exportBtn = document.getElementById('historyExport');
  const exportPdfBtn = document.getElementById('historyExportPdf');
    if (sensorSel) sensorSel.addEventListener('change', loadHistory);
    if (metricSel) metricSel.addEventListener('change', loadHistory);
    if (rangeSel) rangeSel.addEventListener('change', loadHistory);
    if (refreshBtn) refreshBtn.addEventListener('click', loadHistory);
    if (exportBtn) exportBtn.addEventListener('click', exportHistoryCSV);
  if (exportPdfBtn) exportPdfBtn.addEventListener('click', exportHistoryPDF);
    // initial
    loadHistory();
  }

  /** Global initializer for the history chart section. */
  window.initHistoryChart = initHistoryChart;
  /** Global method to reload historical data based on current selectors. */
  window.loadHistory = loadHistory;
  /** Global method to export the current history chart to PDF. */
  window.exportHistoryPDF = exportHistoryPDF;
})();
