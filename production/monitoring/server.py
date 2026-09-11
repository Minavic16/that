"""
Monitoring Server — HTTP Dashboard API
=======================================

Simple stdlib HTTP server (no flask) serving JSON API endpoints
and a self-contained HTML dashboard for real-time monitoring.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Optional
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)


class MonitoringServer:
    """
    Thread-safe monitoring HTTP server.

    Accepts callable data providers that return current state.
    Serves JSON API endpoints and an HTML dashboard.
    """

    def __init__(
        self,
        health_provider: Callable[[], dict[str, Any]] | None = None,
        market_provider: Callable[[], dict[str, Any]] | None = None,
        account_provider: Callable[[], dict[str, Any]] | None = None,
        strategy_provider: Callable[[], dict[str, Any]] | None = None,
        latency_provider: Callable[[], dict[str, Any]] | None = None,
        spread_provider: Callable[[], dict[str, Any]] | None = None,
        slippage_provider: Callable[[], dict[str, Any]] | None = None,
        drawdown_provider: Callable[[], dict[str, Any]] | None = None,
        experiment_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._providers = {
            "health": health_provider,
            "market": market_provider,
            "account": account_provider,
            "strategy": strategy_provider,
            "latency": latency_provider,
            "spread": spread_provider,
            "slippage": slippage_provider,
            "drawdown": drawdown_provider,
            "experiment": experiment_provider,
        }
        self._lock = threading.Lock()
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None

    def _get_data(self, key: str) -> dict[str, Any]:
        """Thread-safe data provider call."""
        provider = self._providers.get(key)
        if provider is None:
            return {"error": f"No provider for {key}"}
        try:
            return provider()
        except Exception as exc:
            logger.warning("Provider %s failed: %s", key, exc)
            return {"error": str(exc)}

    def start(self, port: int = 8080, host: str = "0.0.0.0") -> None:
        """Start the monitoring server in a background thread."""
        if self._server is not None:
            logger.warning("Server already running")
            return

        server_ref = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/")

                # API endpoints
                api_map = {
                    "/api/health": "health",
                    "/api/market": "market",
                    "/api/account": "account",
                    "/api/strategy": "strategy",
                    "/api/latency": "latency",
                    "/api/spread": "spread",
                    "/api/slippage": "slippage",
                    "/api/drawdown": "drawdown",
                    "/api/experiment": "experiment",
                }

                if path in api_map:
                    self._send_json(server_ref._get_data(api_map[path]))

                elif path.startswith("/api/percentiles/"):
                    metric = path.split("/api/percentiles/", 1)[1]
                    data = server_ref._get_percentile(metric)
                    self._send_json(data)

                elif path == "/api/dashboard":
                    data = server_ref._get_dashboard()
                    self._send_json(data)

                elif path == "" or path == "/":
                    self._send_html(DASHBOARD_HTML)

                else:
                    self._send_json({"error": "Not found"}, status=404)

            def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
                body = json.dumps(data, default=str, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(body)

            def _send_html(self, html: str) -> None:
                body = html.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:
                # Suppress default access log
                pass

        self._server = HTTPServer((host, port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("Monitoring server started on %s:%d", host, port)

    def stop(self) -> None:
        """Stop the monitoring server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("Monitoring server stopped")

    def _get_percentile(self, metric: str) -> dict[str, Any]:
        """Get percentile data for a specific metric."""
        data = self._get_data(metric)
        if "error" in data:
            return data
        percentiles = data.get("percentiles", data)
        return {
            "metric": metric,
            "percentiles": percentiles,
        }

    def _get_dashboard(self) -> dict[str, Any]:
        """Combine all providers into a single dashboard response."""
        return {
            "health": self._get_data("health"),
            "market": self._get_data("market"),
            "account": self._get_data("account"),
            "strategy": self._get_data("strategy"),
            "latency": self._get_data("latency"),
            "spread": self._get_data("spread"),
            "slippage": self._get_data("slippage"),
            "drawdown": self._get_data("drawdown"),
            "experiment": self._get_data("experiment"),
        }


# ---------------------------------------------------------------------------
# Self-contained HTML Dashboard
# ---------------------------------------------------------------------------

DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>NestQuant Monitoring</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--surface:#161b22;--border:#30363d;
  --text:#e6edf3;--muted:#8b949e;--accent:#58a6ff;
  --green:#3fb950;--yellow:#d29922;--orange:#db6d28;--red:#f85149;
}
body{background:var(--bg);color:var(--text);font-family:'SF Mono','Cascadia Code','Consolas',monospace;font-size:13px;line-height:1.5}
h1{font-size:16px;padding:12px 16px;border-bottom:1px solid var(--border);color:var(--accent);font-weight:600}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:12px;padding:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:6px;overflow:hidden}
.card-header{padding:8px 12px;border-bottom:1px solid var(--border);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:0.5px;color:var(--muted)}
.card-body{padding:12px}
.row{display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #21262d}
.row:last-child{border-bottom:none}
.label{color:var(--muted)}
.value{font-weight:500}
.status{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status-green{background:var(--green)}
.status-yellow{background:var(--yellow)}
.status-orange{background:var(--orange)}
.status-red{background:var(--red)}
.status-gray{background:var(--muted)}
.insufficient{color:var(--muted);font-style:italic}
.bar-container{height:4px;background:#21262d;border-radius:2px;margin-top:4px}
.bar{height:100%;border-radius:2px;transition:width 0.3s}
.bar-green{background:var(--green)}
.bar-yellow{background:var(--yellow)}
.bar-orange{background:var(--orange)}
.bar-red{background:var(--red)}
.section-title{font-size:11px;color:var(--muted);margin-top:8px;margin-bottom:4px;text-transform:uppercase}
#last-update{position:fixed;bottom:8px;right:12px;color:var(--muted);font-size:11px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<h1>NestQuant Monitoring Dashboard</h1>
<div class="grid">
  <div class="card">
    <div class="card-header">System Health</div>
    <div class="card-body" id="s-health">Loading...</div>
  </div>
  <div class="card">
    <div class="card-header">Account</div>
    <div class="card-body" id="s-account">Loading...</div>
  </div>
  <div class="card">
    <div class="card-header">Execution Quality</div>
    <div class="card-body" id="s-exec">Loading...</div>
  </div>
  <div class="card">
    <div class="card-header">Strategy Health</div>
    <div class="card-body" id="s-strategy">Loading...</div>
  </div>
  <div class="card">
    <div class="card-header">Drawdown</div>
    <div class="card-body" id="s-drawdown">Loading...</div>
  </div>
  <div class="card">
    <div class="card-header">Experiment Identity</div>
    <div class="card-body" id="s-experiment">Loading...</div>
  </div>
</div>
<div id="last-update"></div>
<script>
const $ = id => document.getElementById(id);
const fmt = (v, d=2) => v != null && isFinite(v) ? Number(v).toFixed(d) : 'N/A';
const pct = v => v != null && isFinite(v) ? (v*100).toFixed(1)+'%' : 'N/A';
const statusDot = ok => `<span class="status ${ok?'status-green':'status-red'}"></span>`;
const insuff = (label='') => `<div class="row"><span class="label">${label}</span><span class="insufficient">INSUFFICIENT DATA</span></div>`;
const row = (l,v,c='') => `<div class="row"><span class="label">${l}</span><span class="value ${c}">${v}</span></div>`;

function renderHealth(d){
  if(!d||d.error){$('s-health').innerHTML=insuff();return;}
  let h='';
  h+=row('Bridge',statusDot(d.bridge_healthy)+(d.bridge_healthy?'Healthy':'Down'));
  h+=row('MT5',statusDot(d.mt5_connected)+(d.mt5_connected?'Connected':'Disconnected'));
  h+=row('Init',d.mt5_initialized?'Yes':'No');
  h+=row('Latency',fmt(d.response_time_ms,1)+' ms');
  h+=row('Failures',d.consecutive_failures||0);
  if(d.last_error)h+=row('Last Error',`<span style="color:var(--red)">${d.last_error}</span>`);
  $('s-health').innerHTML=h;
}

function renderAccount(d){
  if(!d||d.error){$('s-account').innerHTML=insuff();return;}
  let h='';
  h+=row('Balance','$'+fmt(d.balance,2));
  h+=row('Equity','$'+fmt(d.equity,2));
  h+=row('Floating P&L','$'+fmt(d.floating_pnl,2));
  h+=row('Realized P&L','$'+fmt(d.realized_pnl,2));
  h+=row('Daily P&L','$'+fmt(d.daily_pnl,2));
  h+=row('Open Positions',d.open_positions||0);
  $('s-account').innerHTML=h;
}

function renderExec(d){
  if(!d||d.error){$('s-exec').innerHTML=insuff();return;}
  let h='';
  const sp = d.spread||{};
  const sl = d.slippage||{};
  const lat = d.latency||{};
  h+=`<div class="section-title">Spread (pips)</div>`;
  if(sp.count>0){
    h+=row('P50',fmt(sp.P50,2));
    h+=row('P90',fmt(sp.P90,2));
    h+=row('P99',fmt(sp.P99,2));
    h+=row('Samples',sp.count);
  } else h+=insuff('Spread');
  h+=`<div class="section-title">Slippage (pips)</div>`;
  if(sl.count>0){
    h+=row('P50',fmt(sl.P50,2));
    h+=row('P90',fmt(sl.P90,2));
    h+=row('P99',fmt(sl.P99,2));
  } else h+=insuff('Slippage');
  h+=`<div class="section-title">Latency (ms)</div>`;
  if(lat.bridge){
    const b=lat.bridge;
    h+=row('Bridge P50',fmt(b.P50,1));
    h+=row('Bridge P99',fmt(b.P99,1));
  } else h+=insuff('Latency');
  $('s-exec').innerHTML=h;
}

function renderStrategy(d){
  if(!d||d.error){$('s-strategy').innerHTML=insuff();return;}
  let h='';
  h+=row('Total Trades',d.total_trades||0);
  h+=row('Win Rate',d.total_trades>0?pct(d.win_rate):'N/A');
  h+=row('Profit Factor',d.total_trades>0?fmt(d.profit_factor,2):'N/A');
  h+=row('Expectancy',d.total_trades>0?'$'+fmt(d.expectancy,2):'N/A');
  h+=row('Rolling EV',d.total_trades>0?'$'+fmt(d.rolling_ev,2):'N/A');
  h+=row('EV Std',d.total_trades>0?fmt(d.ev_std,2):'N/A');
  h+=row('Positive EV %',d.total_trades>0?pct(d.positive_ev_pct):'N/A');
  h+=row('Current Streak',d.current_losing_streak||0);
  h+=row('Max Losing Streak',d.max_losing_streak||0);
  $('s-strategy').innerHTML=h;
}

function renderDrawdown(d){
  if(!d||d.error){$('s-drawdown').innerHTML=insuff();return;}
  let h='';
  h+=row('Current DD','$'+fmt(d.current_drawdown,2));
  h+=row('Current DD %',fmt(d.drawdown_pct,2)+'%');
  h+=row('Max Peak-to-Trough','$'+fmt(d.peak_to_trough_drawdown,2));
  h+=row('Peak Equity','$'+fmt(d.peak_equity,2));
  if(d.episodes!=null)h+=row('DD Episodes',d.episodes);
  if(d.avg_duration!=null)h+=row('Avg Episode Duration',fmt(d.avg_duration,1)+' bars');
  if(d.clustering_ratio!=null)h+=row('Clustering Ratio',fmt(d.clustering_ratio,3));
  $('s-drawdown').innerHTML=h;
}

function renderExperiment(d){
  if(!d||d.error){$('s-experiment').innerHTML=insuff();return;}
  let h='';
  h+=row('Experiment ID',d.experiment_id||'N/A');
  h+=row('Strategy',d.strategy||'N/A');
  h+=row('Version',d.version||'N/A');
  if(d.params){
    for(const[k,v] of Object.entries(d.params)){
      h+=row(k,typeof v==='number'?fmt(v,4):v);
    }
  }
  $('s-experiment').innerHTML=h;
}

async function poll(){
  try{
    const r=await fetch('/api/dashboard');
    const d=await r.json();
    renderHealth(d.health);
    renderAccount(d.account);
    renderExec({spread:d.spread,slippage:d.slippage,latency:d.latency});
    renderStrategy(d.strategy);
    renderDrawdown(d.drawdown);
    renderExperiment(d.experiment);
    const now=new Date().toLocaleTimeString();
    $('last-update').textContent='Last update: '+now;
  }catch(e){
    $('last-update').textContent='Connection lost: '+e.message;
  }
}
poll();
setInterval(poll,5000);
</script>
</body>
</html>"""
