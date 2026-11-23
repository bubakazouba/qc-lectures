// Shared helpers for all three layouts. Data comes from ../data.json (built from the Drive folder).
window.QC = (function () {
  const COLORS = {
    foundations: "#3b82f6", oracles: "#8b5cf6", nonlocality: "#ec4899", grover: "#f59e0b",
    measurement: "#14b8a6", shor: "#ef4444", hardware: "#64748b", optimization: "#22c55e",
    challenges: "#eab308", crypto: "#f97316", qec: "#06b6d4", complexity: "#a855f7",
    ml: "#10b981", manybody: "#6366f1",
  };
  async function load(base) {
    const r = await fetch((base ?? "../") + "data.json", { cache: "no-cache" });
    const d = await r.json();
    d.byId = Object.fromEntries(d.lectures.map((l) => [l.id, l]));
    d.trackById = Object.fromEntries(d.tracks.map((t) => [t.id, t]));
    // Course order: by number, with the hardware series after lecture 18.
    const key = (l) => (l.num != null ? l.num : 18 + parseInt(l.id.slice(1)) / 10);
    d.ordered = [...d.lectures].sort((a, b) => key(a) - key(b));
    // Fix relative image paths inside homework HTML.
    d.lectures.forEach((l) => (l.homework = l.homework.replaceAll('src="img/', `src="${base || "../"}img/`)));
    return d;
  }
  const label = (l) => (l.num != null ? `Lecture ${l.num}` : l.id === "H5" ? "Guest lecture" : `Hardware ${l.id.slice(1)}/4`);
  const thumb = (l) => (l.yt ? `https://i.ytimg.com/vi/${l.yt}/hqdefault.jpg` : null);
  const embed = (l) => (l.yt ? `https://www.youtube-nocookie.com/embed/${l.yt}?rel=0` : null);
  const drivePreview = (n) => (n.id ? `https://drive.google.com/file/d/${n.id}/preview` : null);
  const fmtDate = (iso) => {
    if (!iso) return "";
    const [y, m, d] = iso.split("-").map(Number);
    return new Date(y, m - 1, d).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  return { load, COLORS, label, thumb, embed, drivePreview, fmtDate, esc };
})();
