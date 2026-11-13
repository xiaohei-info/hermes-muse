"""Host-authenticated read-only Muse views: Feed, ideas, goals, recent runs, open findings and the last health check."""

import importlib.util
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request

# Dashboard imports this file independently of the CLI plugin package.
_root = Path(__file__).resolve().parent.parent
_package = "_hermes_muse_views_" + __import__("hashlib").sha256(str(_root).encode()).hexdigest()[:16]
if _package not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_package, _root / "hermes_muse/__init__.py",
                                                   submodule_search_locations=[str(_root / "hermes_muse")])
    sys.modules[_package] = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(sys.modules[_package])
_views = __import__(_package + ".views", fromlist=["Views"])
_host = __import__(_package + ".host.dashboard", fromlist=["home_for"])
_health = __import__(_package + ".health", fromlist=["load"])
router = APIRouter()


def home(selected_profile=None):
    try:
        return _host.home_for(selected_profile)
    except _host.Unavailable as exc:
        raise HTTPException(404, str(exc)) from exc


def read(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except _views.NotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(503, "Stored Muse data unavailable; no repair performed") from exc


@router.get("/capabilities")
def capabilities(selected_profile: str | None = None):
    return {"read_only": True, "profile": selected_profile or home().name,
            "features": ["feed", "ideas", "goals", "runs", "findings", "health", "pagination"]}


@router.get("/feed")
def feed(topic: str | None = None, query: str | None = None, cursor: str | None = None,
         limit: int = Query(25, ge=1, le=100), selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).feed, query=query, topic=topic, cursor=cursor, limit=limit)


@router.get("/feed/{object_id}")
def article(object_id: str, offset: int = Query(0, ge=0), length: int = Query(12000, ge=1, le=24000),
            revision: str | None = None, selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).article, "feed", object_id, offset, length, revision)


@router.get("/ideas")
def ideas(cursor: str | None = None, limit: int = Query(25, ge=1, le=100), selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).ideas, cursor=cursor, limit=limit)


@router.get("/goals")
def goals(cursor: str | None = None, limit: int = Query(25, ge=1, le=100),
          status: str | None = Query(None, pattern="^(open|closed)$"), selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).goals, status=status, cursor=cursor, limit=limit)


@router.get("/goals/{object_id}")
def goal(object_id: str, offset: int = Query(0, ge=0), length: int = Query(12000, ge=1, le=24000),
         revision: str | None = None, selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).article, "goal", object_id, offset, length, revision)


@router.get("/runs")
def runs(cursor: str | None = None, limit: int = Query(25, ge=1, le=100), selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).runs, cursor=cursor, limit=limit)


@router.get("/findings")
def findings(cursor: str | None = None, limit: int = Query(25, ge=1, le=100), selected_profile: str | None = None):
    return read(_views.Views(home(selected_profile)).findings, cursor=cursor, limit=limit)


@router.get("/health")
def health(selected_profile: str | None = None):
    """The profile's last muse/health.json as written by the health cron; never runs a check."""
    return _health.load(home(selected_profile)) or {"available": False}


@router.get("/profiles")
def profiles(request: Request):
    _host.require_token(request)
    return _host.profiles()
