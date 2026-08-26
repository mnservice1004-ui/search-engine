import json
import re
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext


PHONE_RE = re.compile(r"^0\d{8,10}$")
ALLOWED_FLOORS = {"1층", "2층", "3층"}


def digits(value):
    return re.sub(r"\D", "", str(value or ""))


def validate_tasks(tasks):
    errors = []
    warnings = []
    if not isinstance(tasks, list):
        return ["최상위 JSON 값은 배열이어야 합니다."], warnings

    seen = set()
    for index, task in enumerate(tasks, start=1):
        if not isinstance(task, dict):
            errors.append(f"{index}번 항목: 객체가 아닙니다.")
            continue
        task_id = str(task.get("id") or "").strip()
        name = str(task.get("name") or "").strip()
        if not task_id:
            errors.append(f"{index}번 항목: id가 비어 있습니다.")
        elif task_id in seen:
            errors.append(f"{index}번 항목: id {task_id}가 중복됩니다.")
        seen.add(task_id)
        if not name:
            errors.append(f"{task_id or index}: name이 비어 있습니다.")
        floor = str(task.get("floor") or "").strip()
        if floor and floor not in ALLOWED_FLOORS:
            errors.append(f"{task_id or index}: floor 값이 1층, 2층, 3층 중 하나가 아닙니다.")
        if not str(task.get("place") or "").strip():
            warnings.append(f"{task_id or index}: place가 비어 있습니다.")

        phone = digits(task.get("phone"))
        if phone and not PHONE_RE.fullmatch(phone):
            errors.append(f"{task_id or index}: 공식 업무전화 형식을 확인하십시오.")
        if phone and not str(task.get("contact_verified_at") or "").strip():
            errors.append(f"{task_id or index}: 연락처 최종 확인일이 없습니다.")
        if not phone:
            warnings.append(f"{task_id or index}: 공식 업무전화가 없습니다.")

    if len(tasks) != 63:
        warnings.append(f"현재 기준 63건과 다릅니다. 실제 건수: {len(tasks)}건")
    return errors, warnings


class DataTool(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("보건민원 데이터 검증 도구")
        self.geometry("820x560")
        self.source = None
        self.report = ""

        top = tk.Frame(self)
        top.pack(fill="x", padx=14, pady=12)
        tk.Button(top, text="tasks.json 선택", command=self.choose_file).pack(side="left")
        tk.Button(top, text="검증 보고서 저장", command=self.save_report).pack(side="left", padx=8)
        self.path_label = tk.Label(top, text="파일을 선택하십시오.", anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True)

        self.output = scrolledtext.ScrolledText(self, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True, padx=14, pady=(0, 14))

    def choose_file(self):
        selected = filedialog.askopenfilename(filetypes=[("JSON 파일", "*.json")])
        if not selected:
            return
        self.source = Path(selected)
        self.path_label.config(text=str(self.source))
        try:
            tasks = json.loads(self.source.read_text(encoding="utf-8"))
            errors, warnings = validate_tasks(tasks)
        except Exception as exc:
            messagebox.showerror("읽기 실패", str(exc))
            return

        lines = [
            "보건민원 데이터 검증 보고서",
            f"검증일: {date.today().isoformat()}",
            f"파일: {self.source}",
            f"오류: {len(errors)}건 / 경고: {len(warnings)}건",
            "",
            "[오류]",
            *(errors or ["없음"]),
            "",
            "[경고]",
            *(warnings or ["없음"]),
        ]
        self.report = "\n".join(lines)
        self.output.delete("1.0", "end")
        self.output.insert("1.0", self.report)
        if errors:
            messagebox.showwarning("검증 실패", "오류를 수정한 뒤 다시 검증하십시오.")
        else:
            messagebox.showinfo("검증 통과", "오류가 없습니다. 경고 항목은 운영 전 확인하십시오.")

    def save_report(self):
        if not self.report:
            messagebox.showwarning("저장할 내용 없음", "먼저 JSON 파일을 검증하십시오.")
            return
        target = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt")],
            initialfile="data_validation_report.txt",
        )
        if target:
            Path(target).write_text(self.report, encoding="utf-8")
            messagebox.showinfo("저장 완료", target)


if __name__ == "__main__":
    DataTool().mainloop()
