const form = document.getElementById('search-form');
const statusEl = document.getElementById('status');
const errorsEl = document.getElementById('errors');
const resultsCard = document.getElementById('results-card');
const submitBtn = document.getElementById('submit-btn');
const filterNameInput = document.getElementById('filter-name');
const savedFiltersSelect = document.getElementById('saved-filters');
const saveFilterBtn = document.getElementById('save-filter-btn');
const loadFilterBtn = document.getElementById('load-filter-btn');
const runFilterBtn = document.getElementById('run-filter-btn');
const deleteFilterBtn = document.getElementById('delete-filter-btn');
const buyNowCheckbox = document.getElementById('buy_now');
const precioMinInput = document.getElementById('precio_min');
const precioMaxInput = document.getElementById('precio_max');
const activeFiltersEl = document.getElementById('active-filters');
let filtersCache = [];

function numOrNull(id) {
  const el = document.getElementById(id);
  const v = el.value.trim();
  return v === '' ? null : Number(v);
}

function strOrNull(id) {
  const v = document.getElementById(id).value.trim();
  return v || null;
}

function updatePriceFields() {
  const enabled = buyNowCheckbox.checked;
  precioMinInput.disabled = !enabled;
  precioMaxInput.disabled = !enabled;
  if (!enabled) {
    precioMinInput.value = '';
    precioMaxInput.value = '';
  }
}

function normalizeLocation(query) {
  // El backend exige que zip y radio_millas vayan juntos o ninguno.
  if (!query.zip) {
    query.radio_millas = null;
  } else if (!query.radio_millas) {
    query.radio_millas = 100; // default si hay ZIP pero no radio
  }
  return query;
}

function buildPayload() {
  const buyNow = buyNowCheckbox.checked;
  const payload = {
    marca: document.getElementById('marca').value.trim(),
    modelo: strOrNull('modelo'),
    anio: numOrNull('anio'),
    tipo: strOrNull('tipo'),
    anio_min: numOrNull('anio_min'),
    anio_max: numOrNull('anio_max'),
    buy_now: buyNow,
    precio_min: buyNow ? numOrNull('precio_min') : null,
    precio_max: buyNow ? numOrNull('precio_max') : null,
    zip: strOrNull('zip'),
    radio_millas: numOrNull('radio_millas'),
    page_size: numOrNull('page_size') || 50,
  };
  return normalizeLocation(payload);
}

function setField(id, value) {
  const el = document.getElementById(id);
  if (el) {
    if (el.type === 'checkbox') {
      el.checked = Boolean(value);
    } else {
      el.value = value ?? '';
    }
  }
}

function formatMoney(value, moneda) {
  if (value === undefined || value === null) return 'N/D';
  return '$' + value.toLocaleString() + ' ' + (moneda || 'USD');
}

function escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function providerClass(fuente) {
  const key = (fuente || '').toLowerCase();
  if (key.includes('iaai')) return 'badge-iaai';
  if (key.includes('openlane')) return 'badge-openlane';
  return 'badge-default';
}

function renderActiveFilters(payload) {
  activeFiltersEl.innerHTML = '';
  const chips = [];

  const addChip = (label, key) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = '×';
    btn.title = 'Quitar filtro';
    btn.addEventListener('click', () => {
      if (key === 'buy_now') {
        buyNowCheckbox.checked = false;
        updatePriceFields();
      } else if (key === 'anio_range') {
        setField('anio', null);
        setField('anio_min', null);
        setField('anio_max', null);
      } else {
        setField(key, null);
      }
      updateActiveFilters();
    });
    const chip = document.createElement('span');
    chip.className = 'chip';
    chip.textContent = label + ' ';
    chip.appendChild(btn);
    return chip;
  };

  if (payload.marca) chips.push(addChip(`Marca: ${payload.marca}`, 'marca'));
  if (payload.modelo) chips.push(addChip(`Modelo: ${payload.modelo}`, 'modelo'));
  if (payload.tipo) chips.push(addChip(`Tipo: ${payload.tipo}`, 'tipo'));

  if (payload.anio) {
    chips.push(addChip(`Año: ${payload.anio}`, 'anio'));
  } else if (payload.anio_min !== null || payload.anio_max !== null) {
    const min = payload.anio_min ?? '';
    const max = payload.anio_max ?? '';
    chips.push(addChip(`Año: ${min}-${max}`, 'anio_range'));
  }

  if (payload.buy_now) {
    const precioLabel = `Buy Now: ${payload.precio_min ?? 0} - ${payload.precio_max ?? '∞'} USD`;
    chips.push(addChip(precioLabel, 'buy_now'));
  }

  if (payload.zip && payload.radio_millas) {
    chips.push(addChip(`ZIP ${payload.zip} · ${payload.radio_millas} mi`, 'zip'));
  }

  if (chips.length) {
    const clear = document.createElement('button');
    clear.type = 'button';
    clear.textContent = 'Limpiar';
    clear.className = 'secondary';
    clear.style.width = 'auto';
    clear.style.padding = '.35rem .75rem';
    clear.addEventListener('click', clearFilters);

    const label = document.createElement('span');
    label.textContent = 'Filtros activos:';
    label.style.color = 'var(--muted)';
    label.style.fontSize = '.85rem';
    activeFiltersEl.appendChild(label);

    chips.forEach(c => activeFiltersEl.appendChild(c));
    activeFiltersEl.appendChild(clear);
  }
}

function updateActiveFilters() {
  renderActiveFilters(buildPayload());
}

function clearFilters() {
  form.reset();
  buyNowCheckbox.checked = false;
  updatePriceFields();
  updateActiveFilters();
  resultsCard.style.display = 'none';
  resultsCard.innerHTML = '';
  statusEl.textContent = '';
}

async function loadFilters() {
  try {
    const res = await fetch('/api/filtros');
    if (!res.ok) throw new Error('Error cargando filtros: ' + res.status);
    filtersCache = await res.json();
    savedFiltersSelect.innerHTML = '<option value="">— Seleccionar —</option>';
    for (const f of filtersCache) {
      const opt = document.createElement('option');
      opt.value = f.id;
      opt.textContent = f.nombre;
      savedFiltersSelect.appendChild(opt);
    }
  } catch (err) {
    errorsEl.textContent = err.message;
  }
}

function getSelectedFilter() {
  const id = savedFiltersSelect.value;
  return filtersCache.find(f => f.id === id);
}

function loadFilterIntoForm(filt) {
  if (!filt) return;
  const q = filt.query;
  setField('marca', q.marca);
  setField('modelo', q.modelo);
  setField('anio', q.anio);
  setField('tipo', q.tipo);
  setField('anio_min', q.anio_min);
  setField('anio_max', q.anio_max);
  setField('buy_now', q.buy_now);
  updatePriceFields();
  setField('precio_min', q.precio_min);
  setField('precio_max', q.precio_max);
  setField('zip', q.zip);
  setField('radio_millas', q.radio_millas);
  setField('page_size', q.page_size);
  filterNameInput.value = filt.nombre;
  updateActiveFilters();
}

function skeletonTable(rows = 5) {
  const head = `
    <thead>
      <tr>
        <th>Imagen</th><th>Vehículo</th><th>Año</th><th>Precio</th>
        <th>Odómetro</th><th>Motor</th><th>VIN</th><th>Fuente</th><th></th>
      </tr>
    </thead>
  `;
  let body = '';
  for (let i = 0; i < rows; i++) {
    body += `
      <tr>
        <td data-label="Imagen"><div class="skeleton" style="width:80px;height:60px"></div></td>
        <td data-label="Vehículo"><div class="skeleton" style="width:70%"></div></td>
        <td data-label="Año"><div class="skeleton" style="width:40%"></div></td>
        <td data-label="Precio"><div class="skeleton" style="width:50%"></div></td>
        <td data-label="Odómetro"><div class="skeleton" style="width:60%"></div></td>
        <td data-label="Motor"><div class="skeleton" style="width:55%"></div></td>
        <td data-label="VIN"><div class="skeleton" style="width:80%"></div></td>
        <td data-label="Fuente"><div class="skeleton" style="width:50%"></div></td>
        <td data-label=""><div class="skeleton" style="width:30px"></div></td>
      </tr>
    `;
  }
  return `<div class="table-wrap"><table>${head}<tbody>${body}</tbody></table></div>`;
}

function showSkeleton(rows = 5) {
  resultsCard.style.display = 'block';
  resultsCard.innerHTML = skeletonTable(rows);
}

async function doSearch(payload) {
  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="spinner"></span> Buscando...';
  statusEl.textContent = '';
  errorsEl.textContent = '';
  resultsCard.innerHTML = '';
  showSkeleton(5);

  try {
    const res = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error('Error del servidor: ' + res.status + ' ' + text);
    }
    const data = await res.json();
    renderResults(data);
  } catch (err) {
    statusEl.textContent = '';
    errorsEl.textContent = 'Error: ' + err.message;
    resultsCard.style.display = 'none';
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = 'Buscar';
  }
}

function groupByProvider(items) {
  const groups = {};
  for (const item of items) {
    const key = item.fuente || 'Otro';
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

function renderVehicleRow(v) {
  const badgeClass = providerClass(v.fuente);
  const priceClass = v.precio ? 'price' : 'price none';
  const priceText = formatMoney(v.precio, v.moneda);
  const extras = [];
  if (v.dano_primario) extras.push(`Daño: ${escapeHtml(v.dano_primario)}`);
  if (v.estado) extras.push(`Estado: ${escapeHtml(v.estado)}`);
  if (v.sucursal) extras.push(`Sucursal: ${escapeHtml(v.sucursal)}`);
  const subtitle = extras.length ? `<div style="font-size:.8rem;color:var(--muted);margin-top:.2rem">${extras.join(' · ')}</div>` : '';

  return `
    <tr>
      <td data-label="Imagen">${v.imagen_url ? `<img src="${v.imagen_url}" alt="" loading="lazy" />` : ''}</td>
      <td data-label="Vehículo">
        <div>${escapeHtml(v.titulo || '')}</div>
        ${subtitle}
      </td>
      <td data-label="Año">${v.anio ?? ''}</td>
      <td data-label="Precio" class="${priceClass}">${priceText}</td>
      <td data-label="Odómetro">${escapeHtml(v.odometro || '')}</td>
      <td data-label="Motor">${escapeHtml(v.motor || '')}</td>
      <td data-label="VIN">${escapeHtml(v.vin || '')}</td>
      <td data-label="Fuente"><span class="badge ${badgeClass}">${escapeHtml(v.fuente || '')}</span></td>
      <td data-label="">${v.detalle_url ? `<a class="detail" href="${v.detalle_url}" target="_blank" rel="noopener">Ver</a>` : ''}</td>
    </tr>
  `;
}

function renderResults(data) {
  if (data.errores && data.errores.length) {
    errorsEl.textContent = 'Avisos: ' + data.errores.join(' | ');
  } else {
    errorsEl.textContent = '';
  }

  if (!data.items || !data.items.length) {
    statusEl.textContent = 'No se encontraron vehículos.';
    resultsCard.innerHTML = `
      <div class="empty-state">
        <h4>Sin resultados</h4>
        <p>Prueba ajustando los filtros de búsqueda.</p>
      </div>
    `;
    resultsCard.style.display = 'block';
    return;
  }

  statusEl.textContent = `${data.total} resultado(s) encontrados.`;

  const groups = groupByProvider(data.items);
  let html = '';
  for (const [fuente, items] of Object.entries(groups)) {
    const badgeClass = providerClass(fuente);
    html += `
      <div class="provider-section">
        <div class="provider-header">
          <h3><span class="badge ${badgeClass}">${escapeHtml(fuente)}</span></h3>
          <span class="provider-count">${items.length} vehículo(s)</span>
        </div>
        <div class="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Imagen</th><th>Vehículo</th><th>Año</th><th>Precio</th>
                <th>Odómetro</th><th>Motor</th><th>VIN</th><th>Fuente</th><th></th>
              </tr>
            </thead>
            <tbody>
              ${items.map(renderVehicleRow).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  }

  resultsCard.innerHTML = html;
  resultsCard.style.display = 'block';
}

/* Event listeners */
saveFilterBtn.addEventListener('click', async () => {
  const nombre = filterNameInput.value.trim();
  if (!nombre) {
    errorsEl.textContent = 'Escribe un nombre para guardar el filtro.';
    return;
  }
  const payload = buildPayload();
  if (!payload.marca) {
    errorsEl.textContent = 'La marca es obligatoria para guardar un filtro.';
    return;
  }
  try {
    const res = await fetch('/api/filtros', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nombre, query: payload }),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error('Error del servidor: ' + res.status + ' ' + text);
    }
    await loadFilters();
    statusEl.textContent = 'Filtro guardado.';
  } catch (err) {
    errorsEl.textContent = 'Error: ' + err.message;
  }
});

loadFilterBtn.addEventListener('click', () => {
  const filt = getSelectedFilter();
  if (!filt) {
    errorsEl.textContent = 'Selecciona un filtro de la lista.';
    return;
  }
  loadFilterIntoForm(filt);
  statusEl.textContent = `Filtro cargado: ${filt.nombre}`;
});

runFilterBtn.addEventListener('click', async () => {
  const filt = getSelectedFilter();
  if (!filt) {
    errorsEl.textContent = 'Selecciona un filtro de la lista.';
    return;
  }
  await doSearch(normalizeLocation({ ...filt.query }));
});

deleteFilterBtn.addEventListener('click', async () => {
  const filt = getSelectedFilter();
  if (!filt) {
    errorsEl.textContent = 'Selecciona un filtro de la lista.';
    return;
  }
  if (!confirm(`Eliminar filtro "${filt.nombre}"?`)) return;
  try {
    const res = await fetch(`/api/filtros/${filt.id}`, { method: 'DELETE' });
    if (!res.ok) throw new Error('Error eliminando filtro: ' + res.status);
    await loadFilters();
    statusEl.textContent = 'Filtro eliminado.';
  } catch (err) {
    errorsEl.textContent = 'Error: ' + err.message;
  }
});

buyNowCheckbox.addEventListener('change', () => {
  updatePriceFields();
  updateActiveFilters();
});

form.addEventListener('input', updateActiveFilters);
form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const payload = buildPayload();
  renderActiveFilters(payload);
  await doSearch(payload);
});

updatePriceFields();
updateActiveFilters();
loadFilters();
