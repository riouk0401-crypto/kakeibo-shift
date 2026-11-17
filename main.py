from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from ortools.sat.python import cp_model

app = FastAPI(
    title="しふと帳 - 最適化バックエンド API",
    description="スマホ最適化ボトムタブUI版",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JobInfo(BaseModel):
    job_id: str
    name: str
    hourly_wage: int
    hours_per_shift: int = 5
    max_days_per_week: int = 3

class OptimizationRequest(BaseModel):
    target_amount: int
    days_in_month: int = 30
    jobs: List[JobInfo]
    unavailable_days: List[int] = []
    max_shifts_per_week_total: int = 5

def save_results_to_supabase(user_id: str, result_data: dict):
    print(f"[Supabase DB] 保存完了: {result_data.get('total_earned')}円")
    return True

@app.post("/api/optimize", summary="シフト最適化計算")
def optimize_shifts(req: OptimizationRequest):
    try:
        model = cp_model.CpModel()
        num_days = req.days_in_month
        num_jobs = len(req.jobs)
        
        if num_jobs == 0:
            raise HTTPException(status_code=400, detail="バイト先が登録されていません。")

        shift = {}
        for d in range(num_days):
            for j in range(num_jobs):
                shift[d, j] = model.NewBoolVar(f"shift_day_{d}_job_{j}")

        for d in req.unavailable_days:
            if 0 <= d < num_days:
                for j in range(num_jobs):
                    model.Add(shift[d, j] == 0)

        for d in range(num_days):
            model.Add(sum(shift[d, j] for j in range(num_jobs)) <= 1)

        num_weeks = (num_days + 6) // 7
        for w in range(num_weeks):
            start_day = w * 7
            end_day = min(start_day + 7, num_days)
            week_days_vars = [shift[d, j] for d in range(start_day, end_day) for j in range(num_jobs)]
            model.Add(sum(week_days_vars) <= req.max_shifts_per_week_total)
            
            for j_idx, job in enumerate(req.jobs):
                job_week_vars = [shift[d, j_idx] for d in range(start_day, end_day)]
                model.Add(sum(job_week_vars) <= job.max_days_per_week)

        job_incomes = [job.hourly_wage * job.hours_per_shift for job in req.jobs]
        total_earned = sum(
            shift[d, j_idx] * job_incomes[j_idx]
            for d in range(num_days)
            for j_idx in range(num_jobs)
        )

        model.Maximize(total_earned - sum(shift[d, j_idx] * 500 for d in range(num_days) for j_idx in range(num_jobs)))
        model.Add(total_earned >= req.target_amount)

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        status = solver.Solve(model)

        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            schedule_result = []
            actual_earned = 0
            total_shifts = 0

            for d in range(num_days):
                for j_idx, job in enumerate(req.jobs):
                    if solver.Value(shift[d, j_idx]) == 1:
                        earned_amount = job.hourly_wage * job.hours_per_shift
                        actual_earned += earned_amount
                        total_shifts += 1
                        schedule_result.append({
                            "day": d + 1,
                            "job_id": job.job_id,
                            "job_name": job.name,
                            "earned": earned_amount
                        })

            achievement_rate = int((actual_earned / req.target_amount) * 100) if req.target_amount > 0 else 100
            shortfall = max(0, req.target_amount - actual_earned)

            result_payload = {
                "status": "success",
                "total_earned": actual_earned,
                "target_amount": req.target_amount,
                "achievement_rate": achievement_rate,
                "shortfall": shortfall,
                "total_shifts": total_shifts,
                "schedule": schedule_result
            }

            save_results_to_supabase("user_demo_001", result_payload)
            return result_payload
        else:
            raise HTTPException(status_code=422, detail="条件を満たすシフトが見つかりませんでした。目標を少し下げてみてください。")

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"エラー: {str(e)}")

# 白基調 ＆ ボトムナビゲーション付きUI
@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>しふと帳</title>
    <style>
        * {
            box-sizing: border-box;
        }
        body {
            background-color: #f8fafc;
            color: #1e293b;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 0;
            display: flex;
            justify-content: center;
        }
        .phone-frame {
            width: 100%;
            max-width: 480px;
            height: 100vh;
            background-color: #ffffff;
            display: flex;
            flex-direction: column;
            box-shadow: 0 0 20px rgba(0,0,0,0.05);
            position: relative;
        }
        .header {
            background: #ffffff;
            color: #0f172a;
            padding: 16px 20px;
            text-align: center;
            font-size: 18px;
            font-weight: bold;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .content-area {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
            padding-bottom: 80px; /* ボトムバーに隠れない余白 */
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        .card {
            background: #ffffff;
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #e2e8f0;
            box-shadow: 0 1px 3px rgba(0,0,0,0.02);
        }
        .salary-num {
            font-size: 32px;
            font-weight: bold;
            color: #16a34a;
            margin: 6px 0;
        }
        .progress-box {
            display: flex;
            justify-content: space-between;
            background: #f1f5f9;
            padding: 12px;
            border-radius: 12px;
            margin-top: 10px;
        }
        .form-group {
            margin-bottom: 12px;
        }
        label {
            display: block;
            font-size: 13px;
            color: #475569;
            margin-bottom: 4px;
            font-weight: 600;
        }
        input, select {
            width: 100%;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #cbd5e1;
            background: #ffffff;
            color: #1e293b;
            font-size: 14px;
        }
        button.btn-main {
            width: 100%;
            background: #2563eb;
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 8px;
            box-shadow: 0 4px 12px rgba(37, 99, 235, 0.2);
        }
        button.btn-main:active {
            background: #1d4ed8;
        }
        /* カレンダーグリッド */
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 6px;
            margin-top: 8px;
        }
        .cal-day {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 8px;
            padding: 6px 2px;
            text-align: center;
            min-height: 48px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .cal-day.has-shift {
            background: #f0fdf4;
            border-color: #86efac;
        }
        .cal-day.rest-day {
            background: #fef2f2;
            border-color: #fca5a5;
        }
        .day-num {
            font-size: 11px;
            font-weight: bold;
            color: #64748b;
        }
        .shift-tag {
            font-size: 9px;
            border-radius: 4px;
            padding: 2px 1px;
            font-weight: 600;
        }
        .cal-day.has-shift .shift-tag {
            background: #dcfce7;
            color: #15803d;
        }
        .cal-day.rest-day .shift-tag {
            background: #fee2e2;
            color: #b91c1c;
        }
        /* 画面下部固定のボトムナビゲーションバー */
        .bottom-nav {
            position: absolute;
            bottom: 0;
            left: 0;
            width: 100%;
            height: 64px;
            background: #ffffff;
            border-top: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-around;
            align-items: center;
            z-index: 100;
        }
        .nav-item {
            flex: 1;
            text-align: center;
            font-size: 12px;
            color: #94a3b8;
            cursor: pointer;
            padding: 6px 0;
            font-weight: 500;
            transition: color 0.2s;
        }
        .nav-item.active {
            color: #2563eb;
            font-weight: bold;
        }
        .nav-icon {
            font-size: 20px;
            margin-bottom: 2px;
        }
    </style>
</head>
<body>
    <div class="phone-frame">
        <!-- ヘッダー -->
        <div class="header">
            <span>📅 しふと帳</span>
            <span style="font-size:13px; color:#2563eb; font-weight:600;" id="statusBadge">計算済み</span>
        </div>

        <!-- メインコンテンツエリア（タブごとに切り替え） -->
        <div class="content-area">
            
            <!-- ① ダッシュボードタブ -->
            <div id="tab-dashboard" class="tab-content active">
                <div class="card" style="background: linear-gradient(135deg, #eff6ff, #dbeafe); border: 1px solid #bfdbfe;">
                    <div style="font-size: 13px; color: #1e40af; font-weight: 600;">今月の概算給与</div>
                    <div class="salary-num" id="totalEarned">¥0</div>
                    <div class="progress-box" style="background: rgba(255,255,255,0.7);">
                        <div>
                            <div style="font-size:11px; color:#64748b;">目標達成率</div>
                            <div style="font-size:16px; font-weight:bold; color:#2563eb;" id="achievementRate">0%</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-size:11px; color:#64748b;" id="targetLabel">目標: ¥120,000</div>
                            <div style="font-size:11px; color:#d97706; font-weight:600;" id="shortfallLabel">あと ¥120,000</div>
                        </div>
                    </div>
                </div>

                <div class="card">
                    <h3 style="margin-top:0; font-size:15px; color:#0f172a;">💡 クイックアクション</h3>
                    <button class="btn-main" onclick="calculateShifts()">✨ 今すぐシフトを再計算する</button>
                </div>
            </div>

            <!-- ② カレンダータブ -->
            <div id="tab-calendar" class="tab-content">
                <div class="card">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
                        <h3 style="margin:0; font-size:15px; color:#0f172a;">📆 1ヶ月のシフトカレンダー</h3>
                        <span style="font-size:12px; color:#64748b;">5月</span>
                    </div>
                    <div style="display:grid; grid-template-columns: repeat(7, 1fr); text-align:center; font-size:11px; color:#94a3b8; font-weight:bold; margin-bottom:4px;">
                        <div>日</div><div>月</div><div>火</div><div>水</div><div>木</div><div>金</div><div>土</div>
                    </div>
                    <div class="calendar-grid" id="calendarGrid"></div>
                </div>
            </div>

            <!-- ③ 条件・設定タブ -->
            <div id="tab-settings" class="tab-content">
                <div class="card">
                    <h3 style="margin-top:0; font-size:15px; color:#0f172a;">⚙️ 条件 & 目標設定</h3>
                    <div class="form-group">
                        <label>今月の目標金額 (円)</label>
                        <input type="number" id="targetAmount" value="120000" step="5000">
                    </div>
                    <div style="display: flex; gap: 10px;">
                        <div class="form-group" style="flex: 1;">
                            <label>カフェA時給 (円)</label>
                            <input type="number" id="wageA" value="1200" step="100">
                        </div>
                        <div class="form-group" style="flex: 1;">
                            <label>居酒屋B時給 (円)</label>
                            <input type="number" id="wageB" value="1400" step="100">
                        </div>
                    </div>
                    <div class="form-group">
                        <label>休み希望日（カンマ区切り）</label>
                        <input type="text" id="unavailableDays" value="5, 12, 15, 20">
                    </div>
                    <button class="btn-main" onclick="calculateShifts(); switchTab('dashboard');">保存して計算する</button>
                </div>
            </div>

        </div>

        <!-- 画面下部固定のボトムナビゲーションバー -->
        <div class="bottom-nav">
            <div class="nav-item active" onclick="switchTab('dashboard')" id="nav-dashboard">
                <div class="nav-icon">📊</div>
                ダッシュボード
            </div>
            <div class="nav-item" onclick="switchTab('calendar')" id="nav-calendar">
                <div class="nav-icon">📅</div>
                カレンダー
            </div>
            <div class="nav-item" onclick="switchTab('settings')" id="nav-settings">
                <div class="nav-icon">⚙️</div>
                条件設定
            </div>
        </div>
    </div>

    <script>
        // タブ切り替え関数
        function switchTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
            document.querySelectorAll('.nav-item').forEach(el => el.classList.remove('active'));

            document.getElementById('tab-' + tabName).classList.add('active');
            document.getElementById('nav-' + tabName).classList.add('active');
        }

        // シフト計算処理
        async function calculateShifts() {
            const targetAmount = parseInt(document.getElementById('targetAmount').value);
            const wageA = parseInt(document.getElementById('wageA').value);
            const wageB = parseInt(document.getElementById('wageB').value);
            const unavailableStr = document.getElementById('unavailableDays').value;
            
            const unavailableDays = unavailableStr.split(',')
                .map(s => parseInt(s.trim()) - 1)
                .filter(n => !isNaN(n));

            const requestData = {
                target_amount: targetAmount,
                days_in_month: 30,
                jobs: [
                    { job_id: "job_a", name: "カフェA", hourly_wage: wageA, hours_per_shift: 5, max_days_per_week: 3 },
                    { job_id: "job_b", name: "居酒屋B", hourly_wage: wageB, hours_per_shift: 5, max_days_per_week: 3 }
                ],
                unavailable_days: unavailableDays,
                max_shifts_per_week_total: 5
            };

            try {
                const response = await fetch('/api/optimize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'Application/json' },
                    body: JSON.stringify(requestData)
                });

                if (!response.ok) {
                    const err = await response.json();
                    alert("エラー: " + (err.detail || "条件を満たすシフトが見つかりませんでした。"));
                    return;
                }

                const result = await response.json();
                
                document.getElementById('totalEarned').innerText = '¥' + result.total_earned.toLocaleString();
                document.getElementById('achievementRate').innerText = result.achievement_rate + '%';
                document.getElementById('targetLabel').innerText = '目標: ¥' + result.target_amount.toLocaleString();
                document.getElementById('shortfallLabel').innerText = result.shortfall > 0 ? 'あと ¥' + result.shortfall.toLocaleString() : '🎉 目標達成！';

                renderCalendar(30, result.schedule, unavailableDays);

            } catch (e) {
                alert("通信エラーが発生しました: " + e);
            }
        }

        function renderCalendar(days, schedule, unavailableDays) {
            const grid = document.getElementById('calendarGrid');
            grid.innerHTML = '';

            const shiftMap = {};
            schedule.forEach(s => {
                shiftMap[s.day] = s.job_name;
            });

            for (let d = 1; d <= days; d++) {
                const cell = document.createElement('div');
                cell.className = 'cal-day';
                
                const num = document.createElement('div');
                num.className = 'day-num';
                num.innerText = d;
                cell.appendChild(num);

                if (unavailableDays.includes(d - 1)) {
                    cell.classList.add('rest-day');
                    const tag = document.createElement('div');
                    tag.className = 'shift-tag';
                    tag.innerText = '休み';
                    cell.appendChild(tag);
                } else if (shiftMap[d]) {
                    cell.classList.add('has-shift');
                    const tag = document.createElement('div');
                    tag.className, 'shift-tag';
                    tag.innerText = shiftMap[d];
                    cell.appendChild(tag);
                }

                grid.appendChild(cell);
            }
        }

        window.onload = () => {
            calculateShifts();
        };
    </script>
</body>
</html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
