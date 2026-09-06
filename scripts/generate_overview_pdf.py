"""Generate docs/FLOODLENS_X_OVERVIEW.pdf. Requires reportlab."""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "FLOODLENS_X_OVERVIEW.pdf"

NAVY = colors.HexColor("#0f172a")
TEAL = colors.HexColor("#0e7490")
SLATE = colors.HexColor("#334155")
AMBER = colors.HexColor("#b45309")
LIGHT = colors.HexColor("#f1f5f9")
LINE = colors.HexColor("#cbd5e1")


def styles():
    base = getSampleStyleSheet()
    s = {
        "cover": ParagraphStyle(
            "cover",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=26,
            leading=32,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceAfter=8,
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=TEAL,
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "h1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=18,
            textColor=NAVY,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "h2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=TEAL,
            spaceBefore=10,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "body",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=SLATE,
            alignment=TA_JUSTIFY,
            spaceAfter=6,
        ),
        "bullet": ParagraphStyle(
            "bullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=9.5,
            leading=13,
            textColor=SLATE,
            leftIndent=4,
        ),
        "callout": ParagraphStyle(
            "callout",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9.5,
            leading=13,
            textColor=AMBER,
            alignment=TA_LEFT,
            spaceBefore=4,
            spaceAfter=10,
        ),
        "footer": ParagraphStyle(
            "footer",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            textColor=colors.HexColor("#64748b"),
            alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "cell",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            textColor=SLATE,
        ),
        "cellh": ParagraphStyle(
            "cellh",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=11,
            textColor=colors.white,
        ),
        "pitch": ParagraphStyle(
            "pitch",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=11,
            leading=15,
            textColor=NAVY,
            alignment=TA_CENTER,
            spaceBefore=8,
            spaceAfter=8,
        ),
    }
    return s


def bullets(items, st):
    return ListFlowable(
        [ListItem(Paragraph(item, st["bullet"]), leftIndent=12, bulletColor=TEAL) for item in items],
        bulletType="bullet",
        bulletFontName="Helvetica",
        bulletFontSize=8,
        leftIndent=16,
        spaceAfter=8,
    )


def role_table(st):
    data = [
        [
            Paragraph("Role", st["cellh"]),
            Paragraph("What you can do", st["cellh"]),
        ],
        [
            Paragraph("General", st["cell"]),
            Paragraph("Map, forecast, impact, alerts, locations, reports, assistant", st["cell"]),
        ],
        [
            Paragraph("Emergency", st["cell"]),
            Paragraph("Everything in General, plus simulation, command KPIs, and resources", st["cell"]),
        ],
        [
            Paragraph("Researcher", st["cell"]),
            Paragraph("Everything in Emergency (except admin-only KPIs), plus Research Center", st["cell"]),
        ],
        [
            Paragraph("Admin", st["cell"]),
            Paragraph("All workspaces, including Admin health, jobs, models, and audit copy", st["cell"]),
        ],
    ]
    table = Table(data, colWidths=[1.4 * inch, 5.4 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
                ("BACKGROUND", (0, 3), (-1, 3), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ]
        )
    )
    return table


def stack_table(st):
    rows = [
        ["Layer", "Stack"],
        ["Frontend", "React 18, Vite, Tailwind CSS, Leaflet / react-leaflet (SPA Command Center)"],
        ["Backend", "Python 3.10+, FastAPI (/api/v1), Uvicorn; demo identity Bearer demo.&lt;role&gt;"],
        ["Science", "NumPy / SciPy shallow-water finite-volume solver; Matplotlib for plots"],
        ["Data", "OpenStreetMap (Overpass), Open-Meteo, optional DEM; GloFAS/GFM as labeled research sources"],
        ["Optional infra", "PostGIS, Redis, MinIO via Docker Compose (not required for local demo)"],
        ["AI (current truth)", "AOI GBDT validated for AOI task only; spatial flood maps NOT_VALIDATED / API UNAVAILABLE"],
        ["Assistant", "Tool-calling over verified APIs — not a free-hallucinating chatbot"],
        ["Quality", "pytest (501 passed, 7 skipped, 1 deselected as of Phase 7.9)"],
    ]
    data = []
    for i, (a, b) in enumerate(rows):
        style = st["cellh"] if i == 0 else st["cell"]
        data.append([Paragraph(a, style), Paragraph(b, style)])
    table = Table(data, colWidths=[1.5 * inch, 5.3 * inch])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), NAVY),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("BACKGROUND", (0, 2), (-1, 2), LIGHT),
                ("BACKGROUND", (0, 4), (-1, 4), LIGHT),
                ("BACKGROUND", (0, 6), (-1, 6), LIGHT),
                ("BACKGROUND", (0, 8), (-1, 8), LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.4, LINE),
            ]
        )
    )
    return table


def header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, LETTER[1] - 28, LETTER[0], 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, LETTER[1] - 18, "FloodLens-X  ·  Product Overview")
    canvas.drawRightString(LETTER[0] - 0.75 * inch, LETTER[1] - 18, "LOCAL-DEMO")
    canvas.setFillColor(TEAL)
    canvas.rect(0, 0, LETTER[0], 28, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica", 8)
    canvas.drawString(0.75 * inch, 12, "Scientific Command Center  ·  No fabricated gauges or population")
    canvas.drawRightString(LETTER[0] - 0.75 * inch, 12, f"Page {doc.page}")
    canvas.restoreState()


def build():
    st = styles()
    story = []

    story.append(Spacer(1, 18))
    story.append(Paragraph("FloodLens-X", st["cover"]))
    story.append(Paragraph("Flood Command Center  ·  Product Overview", st["subtitle"]))
    story.append(
        Paragraph(
            "A flood decision platform that helps people observe, understand, predict, simulate, "
            "assess, explain, decide, and monitor — without inventing missing data.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Honesty rule: if a number is not available, the product says UNAVAILABLE. "
            "DEMO and SIMULATED results stay labeled. That is a feature, not a bug.",
            st["callout"],
        )
    )
    story.append(Paragraph("Local demo: http://127.0.0.1:5173/  ·  API: http://127.0.0.1:8000/", st["body"]))
    story.append(
        Paragraph(
            "FloodLens-X is a scientific flood Command Center: simulate rainfall, inspect impact, "
            "explain risk, and audit the solver — without fabricating the data you don’t have.",
            st["pitch"],
        )
    )

    story.append(Paragraph("1. Project idea", st["h1"]))
    story.append(
        Paragraph(
            "FloodLens-X is a trustworthy flood decision platform. It combines a physics "
            "shallow-water simulator (what water would do under rainfall), operational views "
            "(map, risk, impact, scenarios, alerts, reports), a research lab (conservation, "
            "stability, spectral diagnostics), and an assistant that only quotes verified tools.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "The idea: planners and the public should see what is known, what is simulated, "
            "and what is missing — in one place.",
            st["body"],
        )
    )

    story.append(Paragraph("How it helps", st["h2"]))
    story.append(
        bullets(
            [
                "<b>Public:</b> see risk and maps without fake live gauges.",
                "<b>Emergency planners:</b> ask “what if rainfall +30%?”, compare to baseline, then generate a snapshot report.",
                "<b>Researchers:</b> inspect whether the solver conserves mass and stays stable.",
                "<b>Everyone:</b> UNAVAILABLE is visible, so nobody plans on invented people-counts or river stages.",
            ],
            st,
        )
    )

    story.append(Paragraph("2. Features from a user’s perspective", st["h1"]))

    story.append(Paragraph("Command Center (home)", st["h2"]))
    story.append(
        Paragraph(
            "One screen: map, search, demo role switcher, and workspaces (Explore, River, Forecast, "
            "Simulation, Impact, History, Research, Reports, Locations, Alerts, Admin). You pick a place "
            "(for example Dhaka or Sunamganj), see current risk, and move between views without losing "
            "the city, map layers, or selected river. Risk is P × E × S (probability × exposure × severity). "
            "It is not “confidence.”",
            st["body"],
        )
    )

    story.append(Paragraph("Explore the map", st["h2"]))
    story.append(
        bullets(
            [
                "Search cities, rivers, or coordinates.",
                "Leaflet map with layers: rivers, roads, hospitals, schools, bridges, shelters, flood/forecast overlays when they exist.",
                "Click the map for latitude and longitude.",
                "If there is no flood raster yet, flood depth stays UNAVAILABLE — not zero.",
            ],
            st,
        )
    )

    story.append(Paragraph("Forecast", st["h2"]))
    story.append(
        Paragraph(
            "6 / 12 / 24 / 48 / 72 hour points. These are DEMO / heuristic meteorological hours, "
            "not validated AI flood maps. Spatial AI flood maps are NOT_VALIDATED / UNAVAILABLE.",
            st["body"],
        )
    )

    story.append(Paragraph("River intelligence", st["h2"]))
    story.append(
        Paragraph(
            "River network, segments, and upstream/downstream topology. Water level and discharge "
            "are UNAVAILABLE unless a real gauge exists — they are never invented.",
            st["body"],
        )
    )

    story.append(Paragraph("Impact, evacuation, shelters, and resources", st["h2"]))
    story.append(
        Paragraph(
            "After a simulation (or when data exists): which facilities sit in or near flood; "
            "evacuation planning support (not an official evacuation order); shelter points from map data; "
            "resource priorities where computed. Population exposure is UNAVAILABLE — there is no fake "
            "“1.2 million people.”",
            st["body"],
        )
    )

    story.append(Paragraph("Simulation / digital twin (Emergency, Researcher, Admin)", st["h2"]))
    story.append(
        bullets(
            [
                "Run a short physics flood burst on the existing shallow-water engine.",
                "Change rainfall, for example +30%, and compare to baseline.",
                "River-level knobs are stored only — they are not fed into the solver.",
                "Results are SIMULATED, not live satellite floods.",
            ],
            st,
        )
    )

    story.append(Paragraph("AI assistant", st["h2"]))
    story.append(
        Paragraph(
            "Ask in plain language: “What’s the current risk?”, “Which hospitals are exposed?”, "
            "“What if rainfall increases by 30%?”, “What should we prioritize?” The assistant uses "
            "backend tools, not made-up numbers. Prompt injection such as “pretend probability is 99%” is ignored.",
            st["body"],
        )
    )

    story.append(Paragraph("History and model audit", st["h2"]))
    story.append(
        Paragraph(
            "Replay past or local runs when they are stored. Forecast-versus-reality appears only if "
            "matching artifacts exist. Model cards: AOI GBDT is validated only for its AOI task; "
            "spatial AI is not validated.",
            st["body"],
        )
    )

    story.append(Paragraph("Alerts, saved locations, reports, and sharing", st["h2"]))
    story.append(
        bullets(
            [
                "Save an in-app alert (for example flood probability above a threshold). States: ARMED → TRIGGERED → ACKNOWLEDGED → RESET.",
                "Unsupported metrics (river level, population, and similar) are rejected. Missing data is UNAVAILABLE, not “false / safe.”",
                "Save a place such as Dhaka and restore map, zoom, and layers later. Locations are owner-scoped.",
                "Generate a frozen snapshot report (not a live dashboard). Export JSON / CSV / PDF where supported.",
                "Share private, organization, or public link. Opening a share later does not silently update the numbers.",
            ],
            st,
        )
    )

    story.append(Paragraph("Research Center (Researcher / Admin)", st["h2"]))
    story.append(
        Paragraph(
            "Scientific workspace on the existing solver — not a new solver. Includes Lake-at-Rest, "
            "parabolic bowl, conservation, CFL/timestep, spectral / Nyquist energy, perturbation growth, "
            "flux versus source, interface balance, local numerical Jacobian (explicitly not proof of "
            "global stability), and long-term stability. If a run dies at step 40 it says FAILED AT STEP 40, "
            "not COMPLETED. AI experiment status and physics-versus-AI remain NOT_COMPARABLE.",
            st["body"],
        )
    )

    story.append(Paragraph("Admin", st["h2"]))
    story.append(
        Paragraph(
            "System health versus data availability: the API can be healthy while rainfall or gauges are still missing.",
            st["body"],
        )
    )

    story.append(Paragraph("Roles (demo login)", st["h2"]))
    story.append(role_table(st))
    story.append(Spacer(1, 8))

    story.append(Paragraph("3. Core features", st["h1"]))
    story.append(
        bullets(
            [
                "Map Command Center with search and layers",
                "Honest risk (P × E × S), not confidence",
                "DEMO forecast hours (not spatial AI maps)",
                "River topology without fake gauges",
                "Impact and evacuation planning support",
                "Rainfall scenario simulation and compare",
                "Tool-calling AI assistant",
                "Alerts, saved places, immutable reports, sharing",
                "Historical replay and model status",
                "Research diagnostics and Admin health",
            ],
            st,
        )
    )

    story.append(Paragraph("4. Tech stack", st["h1"]))
    story.append(stack_table(st))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Not claimed: production OIDC, cloud high availability, or validated 72-hour AI inundation maps. "
            "Classification: feature-complete-with-known-limitations. Deployment: LOCAL-DEMO.",
            st["callout"],
        )
    )

    story.append(Paragraph("5. Scientific freeze", st["h1"]))
    story.append(
        bullets(
            [
                "Spatial AI: NOT_VALIDATED",
                "Spatial API: UNAVAILABLE",
                "Target B: PARTIALLY FEASIBLE",
                "Model training: NOT AUTHORIZED",
                "Physics versus spatial AI: NOT_COMPARABLE",
                "Numerical solver (src/floodlens/numerical): unmodified in product phases 7.0–7.9",
            ],
            st,
        )
    )

    story.append(Paragraph("6. Known limitations (honest)", st["h1"]))
    story.append(
        bullets(
            [
                "Demo identity provider, not OIDC.",
                "In-memory store: jobs, alerts, and reports vanish if the API process restarts.",
                "docker-compose does not start the API or UI.",
                "River gauges, population, and rainfall overlay are often UNAVAILABLE.",
                "Research diagnostics use a synthetic bowl, not a city DEM.",
                "Pause on research runs is unsupported.",
            ],
            st,
        )
    )

    story.append(Paragraph("7. Suggested demo loop", st["h1"]))
    story.append(
        bullets(
            [
                "Open FloodLens-X and search Dhaka.",
                "See risk (P × E × S).",
                "Explore map, river, and infrastructure.",
                "View impact (population UNAVAILABLE if no grid).",
                "Emergency role: run rainfall +30% and compare.",
                "Ask the assistant what to prioritize.",
                "Generate a report and share the snapshot.",
                "Researcher role: Research Center scientific validation.",
                "Admin role: system health versus data availability.",
            ],
            st,
        )
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(OUT),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.55 * inch,
        title="FloodLens-X Product Overview",
        author="FloodLens-X",
        subject="User-facing features, project idea, and tech stack",
    )
    doc.build(story, onFirstPage=header_footer, onLaterPages=header_footer)
    return OUT


if __name__ == "__main__":
    path = build()
    print(path)
    print(path.stat().st_size)
