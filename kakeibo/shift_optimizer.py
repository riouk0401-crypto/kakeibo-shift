from ortools.sat.python import cp_model

def main():
    # 1. 最適化モデルの作成
    model = cp_model.CpModel()

    # 2. 各曜日の勤務可能時間の上限
    max_hours = {"月": 5, "火": 4, "水": 5, "木": 4, "金": 5, "土": 6, "日": 0}

    # 3. 変数の定義（「0時間＝お休み」から「最大時間」まで働けるように修正）
    # A店：時給1,200円 / 勤務可能：月・水・金 / 1日0〜6時間（0時間ならお休み）
    work_a = {}
    for day in ["月", "水", "金"]:
        work_a[day] = model.NewIntVar(0, 6, f"work_a_{day}")
        
    # B店：時給1,400円 / 勤務可能：火・木・土 / 1日0〜5時間（0時間ならお休み）
    work_b = {}
    for day in ["火", "木", "土"]:
        work_b[day] = model.NewIntVar(0, 5, f"work_b_{day}")

    # 4. 条件（制約）の追加
    # 曜日ごとの上限時間を超えないようにする
    for day in ["月", "水", "金"]:
        model.Add(work_a[day] <= max_hours[day])
    for day in ["火", "木", "土"]:
        model.Add(work_b[day] <= max_hours[day])

    # ただし、シフトに入る場合は「最低勤務時間」を守る（0時間＝お休みの場合は適用しない）
    # A店は入るなら4時間以上、B店は入るなら3時間以上
    for day in ["月", "水", "金"]:
        # A店で働く場合(>0)、4時間以上にするという条件
        is_working_a = model.NewBoolVar(f"is_working_a_{day}")
        model.Add(work_a[day] >= 4).OnlyEnforceIf(is_working_a)
        model.Add(work_a[day] == 0).OnlyEnforceIf(is_working_a.Not())
        model.Add(work_a[day] >= 4).OnlyEnforceIf(is_working_a)

    # 週の総労働時間が20時間以内
    total_hours = (
        sum(work_a[day] for day in ["月", "水", "金"]) +
        sum(work_b[day] for day in ["火", "木", "土"])
    )
    model.Add(total_hours <= 20)

    # 5. 収入の計算と目標金額の設定
    total_income = (
        sum(work_a[day] * 1200 for day in ["月", "水", "金"]) +
        sum(work_b[day] * 1400 for day in ["火", "木", "土"])
    )
    model.Add(total_income >= 20000)

    # 6. 目的関数（働く時間ができるだけ少なくなるように最適化する）
    model.Minimize(total_hours)

    # 7. ソルバー（計算機）を実行
    solver = cp_model.CpSolver()
    status = solver.Solve(model)

    # 8. 結果の表示
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        print("=== シフト最適化結果 ===")
        print(f"総収入: {solver.Value(total_income)}円")
        print(f"総労働時間: {solver.Value(total_hours)}時間\n")
        
        for day in ["月", "水", "金"]:
            print(f"{day}曜日 (A店): {solver.Value(work_a[day])}時間 (収入: {solver.Value(work_a[day]) * 1200}円)")
        for day in ["火", "木", "土"]:
            print(f"{day}曜日 (B店): {solver.Value(work_b[day])}時間 (収入: {solver.Value(work_b[day]) * 1400}円)")
    else:
        print("条件を満たすシフトが見つかりませんでした。")

if __name__ == "__main__":
    main()