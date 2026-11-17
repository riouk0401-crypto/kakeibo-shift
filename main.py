from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from ortools.sat.python import cp_model
import os

app = FastAPI(
    title="しふと帳 - 最適化バックエンド API",
    description="スマホからの入力を受け取り、Google OR-Toolsで最適な1ヶ月のシフトを計算するAPIサーバー",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class JobInfo(BaseModel):
    job_id: str = Field(..., description="バイトID")
    name: str = Field(..., description="バイト先名")
    hourly_wage: int = Field(..., description="時給（円）")
    hours_per_shift: int = Field(5, description="1回のシフトの標準時間")
    max_days_per_week: int = Field(3, description="週の最大出勤日数上限")

class OptimizationRequest(BaseModel):
    target_amount: int = Field(..., description="今月の目標金額（円）")
    days_in_month: int = Field(30, description="対象日数の長さ（例: 30日）")
    jobs: List[JobInfo] = Field(..., description="登録されているバイト先のリスト")
    unavailable_days: List[int] = Field([], description="休み希望日の日番号リスト")
    max_shifts_per_week_total: int = Field(5, description="週全体の最大出勤日数上限")

def save_results_to_supabase(user_id: str, result_data: dict):
    print(f"[Supabase DB Mock] 結果をデータベースに保存しました: 予想総額 = {result_data.get('total_earned')}円")
    return True

@app.post("/api/optimize", summary="シフト最適化計算エンドポイント")
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

        model.Maximize(
            total_earned - sum(shift[d, j_idx] * 500 for d in range(num_days) for j_idx in range(num_jobs))
        )
        
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
            raise HTTPException(
                status_code=422,
                detail="指定された条件ではシフトを組むことができませんでした。目標金額を少し下げるか、休み希望を減らしてください。"
            )

    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"最適化処理エラー: {str(e)}")

# パワポのイメージに合わせた美しい日本語UI (HTML)
@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>しふと帳 - バイト最適化システム</title>
    <style>
        body {
            background-color: #121212;
            color: #e0e0e0;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            margin: 0;
            padding: 20px;
            display: flex;
            justify-content: center;
        }
        .container {
            width: 100%;
            max-width: 480px;
            background-color: #1e1e1e;
            border-radius: 24px;
            box-shadow: 0 8px 24px rgba(0,0,0,0.6);
            overflow: hidden;
            border: 1px solid #333;
        }
        .header {
            background: linear-gradient(135deg, #2196F3, #1976D2);
            color: white;
            padding: 20px;
            text-align: center;
            font-size: 20px;
            font-weight: bold;
        }
        .content {
            padding: 20px;
        }
        .card {
            background-color: #2a2a2a;
            border-radius: 16px;
            padding: 16px;
            margin-bottom: 16px;
            border: 1px solid #3c3c3c;
        }
        .dashboard-title {
            font-size: 14px;
            color: #aaa;
            margin-bottom: 4px;
        }
        .salary-display {
            font-size: 28px;
            font-weight: bold;
            color: #4CAF50;
            margin-bottom: 8px;
        }
        .progress-box {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-top: 10px;
            background: #1e1e1e;
            padding: 10px 14px;
            border-radius: 10px;
        }
        .form-group {
            margin-bottom: 12px;
        }
        label {
            display: block;
            font-size: 13px;
            color: #bbb;
            margin-bottom: 4px;
        }
        input, select {
            width: 100%;
            padding: 10px;
            border-radius: 8px;
            border: 1px solid #444;
            background-color: #121212;
            color: white;
            font-size: 14px;
            box-sizing: border-box;
        }
        button.btn-primary {
            width: 100%;
            background: linear-gradient(135deg, #2196F3, #1976D2);
            color: white;
            border: none;
            padding: 14px;
            border-radius: 12px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            margin-top: 10px;
            transition: opacity 0.2s;
        }
        button.btn-primary:hover {
            opacity: 0.9;
        }
        .calendar-grid {
            display: grid;
            grid-template-columns: repeat(7, 1fr);
            gap: 6px;
            margin-top: 10px;
        }
        .cal-day {
            background-color: #333;
            border-radius: 8px;
            padding: 8px 4px;
            text-align: center;
            font-size: 12px;
            min-height: 40px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
        }
        .cal-day.has-shift {
            background-color: #1b5e20;
            border: 1px solid #4CAF50;
        }
        .cal-day.rest-day {
            background-color: #b71c1c;
            border: 1px solid #e53935;
        }
        .day-num {
            font-weight: bold;
            color: #ddd;
        }
        .shift-tag {
            font-size: 9px;
            background: rgba(0,0,0,0.3);
            border-radius: 4px;
            padding: 2px;
            margin-top: 2px;
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            📅 しふと帳 (バイト最適化システム)
        </div>
        <div class="content">
            <!-- ダッシュボードカード -->
            <div class="card">
                <div class="dashboard-title">今月の概算給与</div>
                <div class="salary-display" id="totalEarned">¥0</div>
                <div class="progress-box">
                    <div>
                        <div style="font-size:12px; color:#aaa;">目標達成率</div>
                        <div style="font-size:18px; font-weight:bold; color:#2196F3;" id="achievementRate">0%</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-size:12px; color:#aaa;" id="targetLabel">目標: ¥120,000</div>
                        <div style="font-size:12px; color:#ff9800;" id="shortfallLabel">あと ¥120,000</div>
                    </div>
                </div>
            </div>

            <!-- 設定入力カード -->
            <div class="card">
                <h3 style="margin-top:0; font-size:15px; color:#fff;">⚙️ 条件設定 & 目標</h3>
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
                    <label>休み希望日（カンマ区切り例: 5, 12, 15, 20）</label>
                    <input type="text" id="unavailableDays" value="5, 12, 15, 20">
                </div>
                <button class="btn-primary" onclick="calculateShifts()">✨ 最適なシフトを自動計算する</button>
            </div>

            <!-- カレンダー表示カード -->
            <div class="card">
                <h3 style="margin-top:0; font-size:15px; color:#fff;">📆 1ヶ月のシフトカレンダー</h3>
                <div style="display:grid; grid-template-columns: repeat(7, 1fr); text-align:center; font-size:11px; color:#888; margin-bottom:6px;">
                    <div>日</div><div>月</div><div>火</div><div>水</div><div>木</div><div>金</div><div>土</div>
                </div>
                <div class="calendar-grid" id="calendarGrid"></div>
            </div>
        </div>
    </div>

    <script>
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
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(requestData)
                });

                if (!response.ok) {
                    const err = await response.json();
                    alert("エラー: " + (err.detail || "シフトが見つかりませんでした。条件を緩和してください。"));
                    return;
                }

                const result = await response.json();
                
                document.getElementById('totalEarned').innerText = '¥' + result.total_earned.toLocaleString();
                document.getElementById('achievementRate').innerText = result.achievement_rate + '%';
                document.getElementById('targetLabel').innerText = '目標: ¥' + result.target_amount.toLocaleString();
                document.getElementById('shortfallLabel').innerText = result.shortfall > 0 ? 'あと ¥' + result.shortfall.toLocaleString() : '🎉 目標達成！';

                renderCalendar(30, result.schedule, unavailableDays);

            } catch (e) {
                alert("サーバー通信エラーが発生しました: " + e);
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
                    tag.className = 'shift-tag';
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