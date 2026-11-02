"""Barangays and staff jurisdiction.

A report belongs to the barangay whose boundary contains its pin, worked out by the server when it is submitted; a
pin outside every boundary has no barangay. Staff see and act only on reports of their own barangay, and
administrators see everything, including reports with no barangay. Until the first barangay is loaded there are no
jurisdictions to enforce, so all staff work as one desk.

Boundaries are GeoJSON Polygons or MultiPolygons in the database. Checking them needs no external service or
geometry library. Load or replace them with: python -m barangai.barangays <file.geojson>
"""

import argparse
import json
import math
from pathlib import Path

from fastapi import Depends, HTTPException, Request
from sqlalchemy import and_, false, func, or_, select, true
from sqlalchemy.orm import Session, undefer

from .auth import get_current_user
from .db import get_db, session_for_url
from .models import Barangay, DuplicateSuggestion, Report, User

MAX_VERTICES = 20_000


def polygons(boundary: dict):
    return [boundary["coordinates"]] if boundary["type"] == "Polygon" else boundary["coordinates"]


def in_ring(lat: float, lng: float, ring: list) -> bool:
    inside = False
    for start, end in zip(ring, ring[1:], strict=False):
        (x1, y1), (x2, y2) = start[:2], end[:2]
        if (y1 > lat) != (y2 > lat) and lng < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def contains(boundary: dict, lat: float, lng: float) -> bool:
    """Inside the outer ring and outside any holes. A point exactly on an edge may fall to either side."""
    return any(
        in_ring(lat, lng, polygon[0]) and not any(in_ring(lat, lng, hole) for hole in polygon[1:])
        for polygon in polygons(boundary)
    )


def clean_boundary(boundary) -> dict:
    """The boundary's type and coordinates, or ValueError: a bad boundary must never reach the database."""
    if not isinstance(boundary, dict) or boundary.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("A boundary must be a GeoJSON Polygon or MultiPolygon")
    coordinates = boundary.get("coordinates")
    if not isinstance(coordinates, list) or not coordinates:
        raise ValueError("A boundary needs coordinates")
    vertices = 0
    for polygon in [coordinates] if boundary["type"] == "Polygon" else coordinates:
        if not isinstance(polygon, list) or not polygon:
            raise ValueError("A polygon needs an outer ring")
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise ValueError("A ring needs at least four points")
            for point in ring:
                if not (
                    isinstance(point, list)
                    and len(point) >= 2
                    and all(type(value) in {int, float} and math.isfinite(value) for value in point)
                    and -180 <= point[0] <= 180
                    and -90 <= point[1] <= 90
                ):
                    raise ValueError("Boundary points must be valid [longitude, latitude] pairs")
            if ring[0][:2] != ring[-1][:2]:
                raise ValueError("A ring must end where it starts")
            vertices += len(ring)
    if vertices > MAX_VERTICES:
        raise ValueError(f"A boundary may have at most {MAX_VERTICES} points")
    return {"type": boundary["type"], "coordinates": coordinates}


def all_barangays(db: Session):
    return db.scalars(select(Barangay).options(undefer(Barangay.boundary)).order_by(Barangay.name)).all()


def matching(areas, lat: float, lng: float) -> str | None:
    """The id of the area containing the point. Overlapping areas resolve by name, so the answer never varies."""
    return next((area.id for area in areas if contains(area.boundary, lat, lng)), None)


def barangay_id_for(db: Session, lat: float, lng: float) -> str | None:
    return matching(all_barangays(db), lat, lng)


def active(db: Session) -> bool:
    return db.scalar(select(Barangay.id).limit(1)) is not None


def report_filter(db: Session, user: User):
    """Query condition for the reports staff may see. Residents' own-report rule stays with the callers."""
    if user.role != "staff" or not active(db):
        return true()
    # Never compare with a missing id: SQLAlchemy would turn it into IS NULL and show the admin-only reports.
    return Report.barangay_id == user.barangay_id if user.barangay_id else false()


def may_see(db: Session, user: User, report: Report) -> bool:
    if user.role != "staff" or not active(db):
        return True
    return report.barangay_id is not None and report.barangay_id == user.barangay_id


def staff_audience(db: Session, report: Report):
    """Query condition for the staff told about a report: its barangay's staff and every administrator."""
    if not active(db):
        return User.role.in_(("staff", "administrator"))
    administrators = User.role == "administrator"
    if report.barangay_id is None:
        return administrators
    return or_(administrators, and_(User.role == "staff", User.barangay_id == report.barangay_id))


async def requested_decision(request: Request):
    try:
        body = await request.json() if request.path_params.get("suggestion_id") else None
    except ValueError:
        return None  # The route's own validation answers a malformed body.
    return body.get("decision") if isinstance(body, dict) else None


def guard_duplicate_decision(request: Request, decision: str | None = Depends(requested_decision),
                             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Router-level check, because duplicates.py is frozen and its decision route looks up suggestions directly."""
    suggestion_id = request.path_params.get("suggestion_id")
    item = db.get(DuplicateSuggestion, suggestion_id) if suggestion_id else None
    if not item or user.role == "resident":
        return  # The route itself answers these.
    report, candidate = db.get(Report, item.report_id), db.get(Report, item.candidate_report_id)
    if not may_see(db, user, report):
        raise HTTPException(404, "Suggestion not found")
    # The website groups a confirmed pair, and that would fail, leaving it confirmed with no case. Staff can still
    # dismiss the pair.
    if report.barangay_id != candidate.barangay_id and decision != "rejected":
        raise HTTPException(409, "Reports from different barangays cannot be grouped")


def assign_unassigned(db: Session) -> int:
    """Give reports with no barangay the one their pin falls in; assigned reports never change.

    A case stays in one barangay, since its reports share one status: its reports follow its earliest report.
    """
    areas = all_barangays(db)
    case_barangay, assigned = {}, 0
    for report in db.scalars(select(Report).order_by(Report.created_at)):
        if report.barangay_id is None:
            report.barangay_id = (
                case_barangay[report.case_id]
                if report.case_id in case_barangay
                else matching(areas, report.latitude, report.longitude)
            )
            assigned += report.barangay_id is not None
        if report.case_id:
            case_barangay.setdefault(report.case_id, report.barangay_id)
    return assigned


def remove_crossing_suggestions(db: Session) -> int:
    """Pending suggestions saved before these boundaries existed may pair reports that a border now separates."""
    placed = dict(db.execute(select(Report.id, Report.barangay_id)).all())
    crossing = [item for item in db.scalars(select(DuplicateSuggestion).where(DuplicateSuggestion.decision == "pending"))
                if placed[item.report_id] != placed[item.candidate_report_id]]
    for item in crossing:
        db.delete(item)
    return len(crossing)


def count_where(db: Session, *conditions) -> int:
    model = conditions[0].left.table
    return db.scalar(select(func.count()).select_from(model).where(*conditions))


def features_from(data) -> list[tuple[str, dict]]:
    features = data.get("features") if isinstance(data, dict) and data.get("type") == "FeatureCollection" else [data]
    if not isinstance(features, list) or not features:
        raise ValueError("The file has no barangays")
    result = []
    for feature in features:
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            raise ValueError("Each barangay must be a GeoJSON Feature")
        name = (feature.get("properties") or {}).get("name")
        if not isinstance(name, str) or not name.strip() or len(name.strip()) > 120:
            raise ValueError("Each barangay needs a name of up to 120 characters in its properties")
        result.append((name.strip(), clean_boundary(feature.get("geometry"))))
    if len({name for name, _ in result}) != len(result):
        raise ValueError("Barangay names must be unique")
    return result


def import_boundaries(data, dry_run=False) -> dict:
    """Add barangays, or replace the boundary of one with the same name. Validates everything before saving.

    The first load starts enforcement, so a dry run reports what would happen and saves nothing. Reports outside
    every boundary are for administrators only, so loading needs an administrator to exist.
    """
    features = features_from(data)
    with session_for_url() as db:
        if not count_where(db, User.role == "administrator"):
            raise ValueError("Create an administrator account first: only administrators see reports outside every boundary")
        for name, boundary in features:
            existing = db.scalar(select(Barangay).where(Barangay.name == name))
            if existing:
                existing.boundary = boundary
            else:
                db.add(Barangay(name=name, boundary=boundary))
        db.flush()
        assigned = assign_unassigned(db)
        result = {
            "barangays": [name for name, _ in features],
            "reports_assigned": assigned,
            "reports_outside_every_boundary": count_where(db, Report.barangay_id.is_(None)),
            "staff_without_barangay": count_where(db, User.role == "staff", User.barangay_id.is_(None)),
            "suggestions_removed": remove_crossing_suggestions(db),
            "saved": not dry_run,
        }
        if dry_run:
            db.rollback()
        else:
            db.commit()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load barangay boundaries from a GeoJSON file")
    parser.add_argument("file", type=Path, help="A GeoJSON Feature or FeatureCollection with a name in properties")
    parser.add_argument("--dry-run", action="store_true", help="Report what would happen and save nothing")
    args = parser.parse_args()
    print(json.dumps(import_boundaries(json.loads(args.file.read_text(encoding="utf-8")), args.dry_run)))
