// 경로 지도(Leaflet + OpenStreetMap). 출발지·역·도착지를 찍고 실제 동선에 가깝게 그린다.
// - 버스·지하철: ODsay가 준 지나는 정류장·역 좌표를 차례로 이은 선
// - 택시: 카카오 모빌리티가 준 도로 좌표
// - 열차·고속버스: 선로 좌표가 공개 API에 없어 출발역~도착역 직선
// - 도보·좌표가 없는 구간: 앞뒤 지점을 잇는 점선
import { onMounted, onBeforeUnmount, ref, watch } from "vue";
import { POINT_LABEL, legColor } from "../format.js";

const COLOR = { trunk: "#1f5f4a", bus: "#4f9a3a", subway: "#3d4fa1", taxi: "#c07a12", car: "#c07a12", walk: "#7d8783" };
const GHOST = "#9aa5a0";   // 다른 후보

function label(p) {
  const el = document.createElement("span");  // 툴팁은 HTML로 해석되므로 텍스트 노드로 넣는다
  el.textContent = `${POINT_LABEL[p.kind] || p.kind} · ${p.name}`;
  return el;
}

const near = (a, b) => Math.abs(a[0] - b[0]) < 0.0004 && Math.abs(a[1] - b[1]) < 0.0004;

// 지점과 구간 좌표로 그릴 조각 목록을 만든다. 좌표는 [x, y](경도, 위도).
export function routePieces(points, legs) {
  const at = Object.fromEntries((points || []).map((p) => [p.kind, [p.x, p.y]]));
  const pieces = [];
  let cur = at.origin || null;
  const walk = (to) => { if (cur && to && !near(cur, to)) pieces.push({ kind: "walk", coords: [cur, to] }); };
  let detailed = false;
  for (const leg of legs || []) {
    const trunk = (leg.source || "").startsWith("tago") && at.dep_station && at.arr_station;
    if (trunk) {
      walk(at.dep_station);
      pieces.push({ kind: "trunk", coords: [at.dep_station, at.arr_station] });
      cur = at.arr_station;
    } else if (leg.path && leg.path.length >= 2) {
      walk(leg.path[0]);
      pieces.push({ kind: leg.mode, color: legColor(leg), coords: leg.path });
      cur = leg.path[leg.path.length - 1];
      detailed = true;
    }
  }
  walk(at.destination);
  if (!detailed) {  // 동선 좌표가 없으면(예전 계획 등) 지점끼리 잇는다
    return (points || []).slice(1).map((p, i) => {
      const a = points[i];
      return { kind: a.kind === "dep_station" && p.kind === "arr_station" ? "trunk" : "walk", coords: [[a.x, a.y], [p.x, p.y]] };
    });
  }
  return pieces;
}

export default {
  name: "RouteMap",
  props: {
    points: { type: Array, default: () => [] },   // 크게 보여 줄 경로의 지점
    legs: { type: Array, default: () => [] },     // 그 경로의 구간(동선 좌표 path 포함)
    others: { type: Array, default: () => [] },   // 함께 흐리게 보여 줄 다른 후보들(points 배열의 배열)
    height: { type: String, default: "320px" },
  },
  setup(props) {
    const box = ref(null);
    const failed = ref(false);
    const hasTrunk = ref(false);
    let map = null, layer = null;
    let views = { all: [], start: [], end: [] };  // 전체·출발 쪽·도착 쪽 범위([위도, 경도] 목록)

    function focus(which) {
      const pts = views[which];
      if (map && pts.length) map.fitBounds(pts, { padding: [30, 30], maxZoom: 16 });
    }

    function draw() {
      if (!map) return;
      layer.clearLayers();
      const all = [];
      for (const pts of props.others) {
        for (const pc of routePieces(pts, [])) {
          L.polyline(pc.coords.map(([x, y]) => [y, x]), { color: GHOST, weight: 2, opacity: 0.6, dashArray: "4 6" }).addTo(layer);
        }
        pts.forEach((p) => all.push([p.y, p.x]));
      }
      const pieces = routePieces(props.points, props.legs);
      const t = pieces.findIndex((pc) => pc.kind === "trunk");
      hasTrunk.value = t >= 0;
      views = {
        all: [],
        start: t >= 0 ? pieces.slice(0, t + 1).flatMap((pc, i) => (i === t ? [pc.coords[0]] : pc.coords)).map(([x, y]) => [y, x]) : [],
        end: t >= 0 ? pieces.slice(t).flatMap((pc, i) => (i === 0 ? [pc.coords[pc.coords.length - 1]] : pc.coords)).map(([x, y]) => [y, x]) : [],
      };
      for (const pc of pieces) {
        const ll = pc.coords.map(([x, y]) => [y, x]);
        const style = pc.kind === "walk"
          ? { color: COLOR.walk, weight: 3, opacity: 0.9, dashArray: "4 6" }
          : { color: pc.color || COLOR[pc.kind] || COLOR.trunk, weight: pc.kind === "trunk" ? 5 : 4, opacity: 0.9 };
        L.polyline(ll, style).addTo(layer);
        ll.forEach((p) => all.push(p));
      }
      props.points.forEach((p, i) => {
        const end = p.kind === "origin" || p.kind === "destination";
        L.circleMarker([p.y, p.x], { radius: end ? 8 : 6, color: "#fff", weight: 2, fillOpacity: 1,
          fillColor: end ? (p.kind === "origin" ? COLOR.subway : "#a1302b") : COLOR.trunk })
          .bindTooltip(label(p), { permanent: true, direction: i % 2 ? "bottom" : "top", className: "map-label" })
          .addTo(layer);
        all.push([p.y, p.x]);
      });
      views.all = all;
      if (all.length) map.fitBounds(all, { padding: [36, 36], maxZoom: 15 });
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
    watch(() => [props.points, props.legs, props.others], draw, { deep: true });

    return { box, failed, hasTrunk, focus };
  },
  template: `
    <div class="route-map">
      <div v-if="failed" class="map-fallback">지도를 불러오지 못했어요. 인터넷 연결을 확인해 주세요(지도 타일은 OpenStreetMap에서 받아요).</div>
      <div v-else-if="!points.length && !others.length" class="map-fallback">표시할 지점이 없어요.</div>
      <div v-if="hasTrunk" class="map-views" role="group" aria-label="지도 범위">
        <button type="button" class="chip" @click="focus('all')">전체</button>
        <button type="button" class="chip" @click="focus('start')">출발 쪽</button>
        <button type="button" class="chip" @click="focus('end')">도착 쪽</button>
      </div>
      <div v-show="!failed && (points.length || others.length)" ref="box" class="map-box" :style="{ height }"
           role="img" :aria-label="points.map(p => p.name).join(' → ') || '경로 지도'"></div>
      <p class="map-legend">
        <span class="lg trunk"></span>열차·고속버스 <span class="lg taxi"></span>택시 <span class="lg walk"></span>도보
        <span class="lg-note">· 지하철은 노선 고유색, 버스는 종류별 색(간선 파랑·지선 초록·광역·급행 빨강)이에요.
          버스·지하철은 정류장을, 택시는 도로를 따라 그렸고 열차는 역 사이 직선이에요</span>
      </p>
    </div>`,
};
