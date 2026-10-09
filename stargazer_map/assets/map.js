(function(){
  // Places are embedded by build_site.py as JSON in <script id="places">.
  var places = JSON.parse(document.getElementById('places').textContent);
  var map = L.map('map',{worldCopyJump:true,minZoom:1}).setView([25,10],2);
  var dark = window.matchMedia && matchMedia('(prefers-color-scheme: dark)').matches;
  // Esri gray canvas: no API key needed (CARTO basemaps now require one).
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_' + (dark?'Dark':'Light') + '_Gray_Base/MapServer/tile/{z}/{y}/{x}',{
    maxZoom:16,
    attribution:'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; Esri, HERE, Garmin, &copy; OpenStreetMap contributors'
  }).addTo(map);
  var accent = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim();
  var bounds = [];
  places.forEach(function(p){
    var r = 5 + 4*Math.sqrt(p.count);
    var m = L.circleMarker([p.lat,p.lon],{radius:r,color:accent,weight:1.5,
      fillColor:accent,fillOpacity:.45}).addTo(map);
    var txt = '<b>'+escapeHtml(p.label)+'</b><br>'+p.count+' stargazer'+(p.count>1?'s':'');
    if (p.logins) txt += '<br>' + p.logins.map(function(l){
      return '<a href="https://github.com/'+encodeURIComponent(l)+'" target="_blank" rel="noopener">@'+escapeHtml(l)+'</a>';
    }).join(', ');
    m.bindPopup(txt);
    bounds.push([p.lat,p.lon]);
  });
  if (bounds.length > 1) map.fitBounds(bounds,{padding:[30,30],maxZoom:5});
  else if (bounds.length === 1) map.setView(bounds[0],4);
  function escapeHtml(s){return String(s).replace(/[&<>"']/g,function(c){
    return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];});}
})();
