// 경로 지도(Leaflet + OpenStreetMap). 출발지·역·도착지를 찍고 구간을 이어 그린다.
// 선은 Tool이 준 지점 좌표를 이은 "구간 연결선"이다(실제 도로·선로 모양이 아님).
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { POINT_LABEL } from "../format.js";

const TRUNK = "#1f5f4a";   // 간선(열차·고속버스)
const ACCESS = "#3d4fa1";  // 출발·도착 구간(도보·대중교통·택시)
const GHOST = "#9aa5a0";   // 다른 후보

function label(p) {
  const el = document.createElement("span");  // 툴팁은 HTML로 해석되므로 텍스트 노드로 넣는다
  el.textContent = `${POINT_LABEL[p.kind] || p.kind} · ${p.name}`;
  return el;
}

function segments(points) {
  const out = [];
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    out.push({ a, b, trunk: a.kind === "dep_station" && b.kind === "arr_station" });
  }
  return out;
}

export default {
  name: "RouteMap",
  props: {
    points: { type: Array, default: () => [] },   // 크게 보여 줄 경로
    others: { type: Array, default: () => [] },   // 함께 흐리게 보여 줄 다른 후보들(points 배열의 배열)
    height: { type: String, default: "320px" },
  },
  setup(props) {
    const box = ref(null);
    const failed = ref(false);
    let map = null, layer = null;

    function draw() {
      if (!map) return;
      layer.clearLayers();
      const all = [];
      for (const pts of props.others) {
        for (const s of segments(pts)) {
          L.polyline([[s.a.y, s.a.x], [s.b.y, s.b.x]], { color: GHOST, weight: 2, opacity: 0.6, dashArray: "4 6" }).addTo(layer);
        }
        pts.forEach((p) => all.push([p.y, p.x]));
      }
      for (const s of segments(props.points)) {
        L.polyline([[s.a.y, s.a.x], [s.b.y, s.b.x]], s.trunk
          ? { color: TRUNK, weight: 5, opacity: 0.9 }
          : { color: ACCESS, weight: 3, opacity: 0.9, dashArray: "6 6" }).addTo(layer);
      }
      props.points.forEach((p, i) => {
        const end = p.kind === "origin" || p.kind === "destination";
        L.circleMarker([p.y, p.x], { radius: end ? 8 : 6, color: "#fff", weight: 2, fillOpacity: 1,
          fillColor: end ? (p.kind === "origin" ? ACCESS : "#a1302b") : TRUNK })
          .bindTooltip(label(p), { permanent: true, direction: i % 2 ? "bottom" : "top", className: "map-label" })
          .addTo(layer);
        all.push([p.y, p.x]);
      });
      if (all.length) map.fitBounds(all, { padding: [36, 36], maxZoom: 14 });
    }

    onMounted(() => {
      if (typeof L === "undefined") { failed.value = true; return; }
      map = L.map(box.value, { zoomControl: true, scrollWheelZoom: true, wheelPxPerZoomLevel: 90 }).setView([36.3, 127.4], 7);
      L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);
      layer = L.layerGroup().addTo(map);
      draw();
      setTimeout(() => map && map.invalidateSize(), 50);  // 탭·페이지 전환 직후 크기 보정
    });
    onBeforeUnmount(() => { if (map) { map.remove(); map = null; } });
    watch(() => [props.points, props.others], draw, { deep: true });

    return { box, failed };
  },
  template: `
    <div class="route-map">
      <div v-if="failed" class="map-fallback">지도를 불러오지 못했어요. 인터넷 연결을 확인해 주세요(지도 타일은 OpenStreetMap에서 받아요).</div>
      <div v-else-if="!points.length && !others.length" class="map-fallback">표시할 지점이 없어요.</div>
      <div v-show="!failed && (points.length || others.length)" ref="box" class="map-box" :style="{ height }"
           role="img" :aria-label="points.map(p => p.name).join(' → ') || '경로 지도'"></div>
      <p class="map-legend">
        <span class="lg trunk"></span>열차·고속버스 <span class="lg access"></span>역까지·목적지까지
        <span class="lg-note">· 지점을 이은 구간 연결선이며 실제 도로·선로 모양은 아니에요</span>
      </p>
    </div>`,
};
