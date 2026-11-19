"""Google Calendar 구현체. 최초 1회 브라우저 OAuth 동의 후 token.json을 재사용한다(token·credentials는 커밋 금지).

준비: Google Cloud 프로젝트 → Calendar API 사용 설정 → OAuth 클라이언트(데스크톱 앱) → credentials.json을 프로젝트 루트에.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from backend.agent.judge import Busy
from backend.calendar.base import plan_span

ROOT = Path(__file__).resolve().parents[2]
SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.readonly"]
TZ = "Asia/Seoul"
REMINDER_MIN = (15, 5)


class GoogleCalendar:
    name = "google"

    def __init__(self, calendar_id: str = "primary", token_path: Path = ROOT / "token.json",
                 credentials_path: Path = ROOT / "credentials.json"):
        self.calendar_id, self.token_path, self.credentials_path = calendar_id, token_path, credentials_path

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES) if self.token_path.exists() else None
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(str(self.credentials_path), SCOPES)
                creds = flow.run_local_server(port=0)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return build("calendar", "v3", credentials=creds, cache_discovery=False)

    def get_free_busy(self, day: dt.date, days: int = 1) -> list[Busy]:
        lo = dt.datetime.combine(day, dt.time.min).isoformat() + "+09:00"
        hi = dt.datetime.combine(day + dt.timedelta(days=days), dt.time.min).isoformat() + "+09:00"
        res = self._service().freebusy().query(body={"timeMin": lo, "timeMax": hi, "timeZone": TZ,
                                                     "items": [{"id": self.calendar_id}]}).execute()
        busy = res["calendars"][self.calendar_id]["busy"]

        def local(s):  # freeBusy는 UTC로 줄 수 있어 서울 시각으로 바꾼다
            t = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
            return t.astimezone(dt.timezone(dt.timedelta(hours=9))).replace(tzinfo=None)
        return [Busy("일정", local(b["start"]), local(b["end"])) for b in busy]  # freeBusy는 제목을 주지 않는다

    def upcoming_events(self, start: dt.datetime, days: int = 2) -> list[dict]:
        """앞으로 days일 일정(제목·시작·끝·장소). 종일 일정은 도착 시각이 없어 뺀다. 경로 제안에만 쓴다."""
        lo = start.isoformat(timespec="seconds") + "+09:00"
        hi = (start + dt.timedelta(days=days)).isoformat(timespec="seconds") + "+09:00"
        res = self._service().events().list(calendarId=self.calendar_id, timeMin=lo, timeMax=hi, singleEvents=True,
                                            orderBy="startTime", maxResults=20,
                                            fields="items(summary,location,start,end)").execute()

        def local(v):
            t = dt.datetime.fromisoformat(v.replace("Z", "+00:00"))
            return t.astimezone(dt.timezone(dt.timedelta(hours=9))).replace(tzinfo=None)
        return [{"title": it.get("summary") or "", "start": local(it["start"]["dateTime"]), "end": local(it["end"]["dateTime"]),
                 "location": it.get("location")}
                for it in res.get("items", []) if "dateTime" in it.get("start", {})]

    def create_event(self, plan) -> str:
        start, end = plan_span(plan)
        body = {"summary": f"이동: {plan.title}",
                "description": " → ".join(f"{leg.name or leg.mode}" for leg in (plan.legs or [])),
                "start": {"dateTime": start.isoformat(), "timeZone": TZ},
                "end": {"dateTime": end.isoformat(), "timeZone": TZ},
                # 출발 알림: 이동 일정의 시작 = 나갈 시각이라 15분·5분 전 팝업
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": m} for m in REMINDER_MIN]}}
        return self._service().events().insert(calendarId=self.calendar_id, body=body).execute()["id"]
