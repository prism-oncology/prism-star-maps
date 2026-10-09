(function(){
  // build_site embeds {places, countries: {ISO2: count}, layers} in <script id="map-data">.
  var data = JSON.parse(document.getElementById('map-data').textContent);
  var map = L.map('map',{worldCopyJump:true,minZoom:1}).setView([25,10],2);
  var dark, accent, surface, ink, tiles;
  // Theme-dependent colours; re-read on every `themechange` (see theme.js).
  function readTheme(){
    var t = document.documentElement.dataset.theme;
    dark = t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
    var css = getComputedStyle(document.documentElement);
    accent = css.getPropertyValue('--accent').trim();
    surface = css.getPropertyValue('--card').trim();
    ink = css.getPropertyValue('--fg').trim();
  }
  // Esri gray canvas: no API key needed (CARTO basemaps now require one).
  function setTiles(){
    if (tiles) map.removeLayer(tiles);
    tiles = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_' + (dark?'Dark':'Light') + '_Gray_Base/MapServer/tile/{z}/{y}/{x}',{
      maxZoom:16,
      attribution:'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors &middot; Borders: <a href="https://www.naturalearthdata.com/">Natural Earth</a>'
    }).addTo(map);
  }
  readTheme();
  setTiles();

  // Countries sit below the bubbles whichever layer is switched on last.
  map.createPane('countries').style.zIndex = 350;

  // ---- Bubbles: one per place, area ~ count -------------------------------
  var bubbles = L.layerGroup();
  var bounds = [];
  data.places.forEach(function(p){
    var r = 5 + 4*Math.sqrt(p.count);
    var m = L.circleMarker([p.lat,p.lon],{radius:r,color:accent,weight:1.5,
      fillColor:accent,fillOpacity:.45}).addTo(bubbles);
    var txt = '<b>'+escapeHtml(p.label)+'</b><br>'+plural(p.count);
    if (p.logins) txt += '<br>' + p.logins.map(function(l){
      return '<a href="https://github.com/'+encodeURIComponent(l)+'" target="_blank" rel="noopener">@'+escapeHtml(l)+'</a>';
    }).join(', ');
    m.bindPopup(txt);
    bounds.push([p.lat,p.lon]);
  });

  // ---- Countries: one-hue sequential ramp, log scale ----------------------
  // Blue 100 -> 700. Light mode: few = light, many = dark. Dark mode flips the
  // anchor so "few" recedes into the dark basemap.
  var BLUE = ['#cde2fb','#b7d3f6','#9ec5f4','#86b6ef','#6da7ec','#5598e7','#3987e5',
              '#2a78d6','#256abf','#1c5cab','#184f95','#104281','#0d366b'];
  function ramp(){ return dark ? BLUE.slice().reverse() : BLUE; }
  var counts = data.countries;
  var max = Math.max.apply(null, [1].concat(Object.keys(counts).map(function(k){return counts[k];})));
  // Log scale: a few big countries would otherwise flatten everyone else to the
  // lightest step. 1 stargazer starts at step 200, not 100, so it stays visible.
  function position(n){ return max > 1 ? Math.log(n)/Math.log(max) : 1; }
  function colour(n){ return sample(0.15 + 0.85*position(n)); }

  var countries = L.geoJSON(null,{
    pane:'countries',
    filter:function(f){ return counts[f.id] > 0; },
    style:function(f){ return {fillColor:colour(counts[f.id]),fillOpacity:.85,color:surface,weight:.6}; },
    onEachFeature:function(f, layer){
      layer.bindTooltip('<b>'+escapeHtml(f.properties.name)+'</b><br>'+plural(counts[f.id]),{sticky:true});
      layer.on('mouseover',function(){ layer.setStyle({color:ink,weight:1.5}); });
      layer.on('mouseout',function(){ countries.resetStyle(layer); });
    }
  });
  fetch('assets/countries.geojson').then(function(r){ return r.json(); })
    .then(function(geo){ countries.addData(geo); })
    .catch(function(){ /* file:// or offline: the bubbles still work */ });

  // ---- Legend for the colour scale ----------------------------------------
  var legend = L.control({position:'bottomleft'});
  legend.onAdd = function(){
    var div = L.DomUtil.create('div','map-legend');
    var stops = [];
    for (var i = 0; i <= 10; i++) stops.push(sample(0.15 + 0.85*i/10) + ' ' + (i*10) + '%');
    var ticks = tickValues().map(function(v){
      return '<span style="left:'+(100*position(v)).toFixed(1)+'%">'+v.toLocaleString()+'</span>';
    }).join('');
    div.innerHTML = '<div class="map-legend-title">Stargazers per country</div>'
      + '<div class="map-legend-bar" style="background:linear-gradient(to right,'+stops.join(',')+')"></div>'
      + '<div class="map-legend-ticks">'+ticks+'</div>';
    return div;
  };
  function tickValues(){
    if (max <= 1) return [1];
    var mid = Math.round(Math.sqrt(max));  // halfway on a log scale
    return mid > 1 && mid < max ? [1, mid, max] : [1, max];
  }

  // ---- Layer toggles (checkboxes: either, both or none) --------------------
  var overlays = {'Countries': countries, 'Bubbles': bubbles};
  var names = {countries: 'Countries', bubbles: 'Bubbles'};
  var KEY = 'stargazer-map:layers';
  var shown = data.layers;
  try { var saved = JSON.parse(localStorage.getItem(KEY)); if (Array.isArray(saved)) shown = saved; } catch(e) {}
  Object.keys(names).forEach(function(k){ if (shown.indexOf(k) >= 0) overlays[names[k]].addTo(map); });
  if (map.hasLayer(countries)) legend.addTo(map);
  L.control.layers(null, overlays, {collapsed:false}).addTo(map);
  map.on('overlayadd overlayremove', function(e){
    if (e.layer === countries) { if (e.type === 'overlayadd') legend.addTo(map); else legend.remove(); }
    var now = Object.keys(names).filter(function(k){ return map.hasLayer(overlays[names[k]]); });
    try { localStorage.setItem(KEY, JSON.stringify(now)); } catch(e) {}
  });

  // ---- Repaint everything colour-dependent when the theme flips ------------
  window.addEventListener('themechange', function(){
    readTheme();
    setTiles();
    bubbles.eachLayer(function(m){ m.setStyle({color:accent,fillColor:accent}); });
    countries.setStyle(countries.options.style);
    if (map.hasLayer(countries)) { legend.remove(); legend.addTo(map); }
  });

  if (bounds.length > 1) map.fitBounds(bounds,{padding:[30,30],maxZoom:5});
  else if (bounds.length === 1) map.setView(bounds[0],4);

  // Linear interpolation along the current ramp, t in [0, 1].
  function sample(t){
    var RAMP = ramp();
    var x = Math.max(0, Math.min(1, t)) * (RAMP.length - 1);
    var i = Math.min(Math.floor(x), RAMP.length - 2), f = x - i;
    var a = hex(RAMP[i]), b = hex(RAMP[i+1]);
    return 'rgb(' + [0,1,2].map(function(c){ return Math.round(a[c] + (b[c]-a[c])*f); }).join(',') + ')';
  }
  function hex(h){ return [1,3,5].map(function(i){ return parseInt(h.substr(i,2),16); }); }
  function plural(n){ return n + ' stargazer' + (n > 1 ? 's' : ''); }
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
})();
