"""Exports Excel et PDF aux couleurs de l'organisation cliente."""
from __future__ import annotations

import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from server.app.models import Organisation


class Feuille:
    """Un tableau à exporter : titre, colonnes, lignes et ligne de total facultative."""

    def __init__(self, nom: str, colonnes: list[str], lignes: list[list], total: list | None = None,
                 largeurs: list[int] | None = None):
        self.nom, self.colonnes, self.lignes, self.total, self.largeurs = nom, colonnes, lignes, total, largeurs


def excel(organisation: Organisation, titre: str, sous_titre: str, feuilles: list[Feuille]) -> bytes:
    classeur = Workbook()
    classeur.remove(classeur.active)
    couleur = organisation.couleur_primaire.lstrip("#").upper()
    fin = Side(style="thin", color="D6DCE8")
    for f in feuilles:
        ws = classeur.create_sheet(f.nom[:31])
        ws.sheet_view.showGridLines = False
        ws["A1"] = f"{organisation.nom} — {titre}"
        ws["A1"].font = Font(bold=True, size=14, color=couleur)
        ws["A2"] = sous_titre
        ws["A2"].font = Font(size=10, color="5B6478")
        ws["A3"] = f"Édité le {datetime.now():%d/%m/%Y à %H:%M}"
        ws["A3"].font = Font(size=9, italic=True, color="8A93A6")
        ws.append([])
        ws.append(f.colonnes)
        ligne_entete = ws.max_row
        for c in ws[ligne_entete]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor=couleur)
            c.alignment = Alignment(vertical="center", wrap_text=True)
        for ligne in f.lignes:
            ws.append(ligne)
        if f.total:
            ws.append(f.total)
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
                c.fill = PatternFill("solid", fgColor="EEF1F8")
        for rangee in ws.iter_rows(min_row=ligne_entete, max_row=ws.max_row):
            for c in rangee:
                c.border = Border(bottom=fin)
        ws.freeze_panes = ws.cell(row=ligne_entete + 1, column=1)
        ws.auto_filter.ref = f"A{ligne_entete}:{get_column_letter(len(f.colonnes))}{ws.max_row}"
        for i, nom in enumerate(f.colonnes, 1):
            largeur = (f.largeurs[i - 1] if f.largeurs else
                       min(45, max(len(str(nom)), *(len(str(l[i - 1])) for l in f.lignes[:300]), 8) + 2)
                       if f.lignes else len(str(nom)) + 4)
            ws.column_dimensions[get_column_letter(i)].width = largeur
    flux = io.BytesIO()
    classeur.save(flux)
    return flux.getvalue()


def pdf(organisation: Organisation, titre: str, sous_titre: str, indicateurs: list[tuple[str, str]],
        feuille: Feuille) -> bytes:
    flux = io.BytesIO()
    primaire = colors.HexColor(organisation.couleur_primaire)
    doc = SimpleDocTemplate(flux, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=14 * mm, title=titre, author=organisation.nom)
    s_titre = ParagraphStyle("titre", fontName="Helvetica-Bold", fontSize=16, textColor=colors.HexColor("#142040"),
                             leading=20)
    s_sous = ParagraphStyle("sous", fontName="Helvetica", fontSize=9.5, textColor=colors.HexColor("#5B6478"))
    s_cellule = ParagraphStyle("cellule", fontName="Helvetica", fontSize=8.5, leading=10.5)

    entete = [Paragraph(f"{organisation.nom}<br/><font size=9 color='#5B6478'>{organisation.slogan}</font>",
                        ParagraphStyle("org", fontName="Helvetica-Bold", fontSize=12, leading=15))]
    if organisation.logo and organisation.logo_type in ("image/png", "image/jpeg"):
        logo = ImageReader(io.BytesIO(organisation.logo))
        entete.insert(0, Image(io.BytesIO(organisation.logo), width=14 * mm,
                               height=14 * mm * logo.getSize()[1] / logo.getSize()[0]))
    elements = [Table([entete], colWidths=[18 * mm, None] if len(entete) == 2 else [None],
                      style=[("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("LEFTPADDING", (0, 0), (-1, -1), 0)]),
                Spacer(1, 6 * mm), Paragraph(titre, s_titre), Paragraph(sous_titre, s_sous), Spacer(1, 5 * mm)]

    if indicateurs:
        cases = [[Paragraph(f"<font size=8 color='#5B6478'>{l}</font><br/><font size=15><b>{v}</b></font>",
                            ParagraphStyle("kpi", leading=19)) for l, v in indicateurs]]
        t = Table(cases, colWidths=[(doc.width - 6 * mm * (len(indicateurs) - 1)) / len(indicateurs)] * len(indicateurs))
        t.setStyle(TableStyle([("BOX", (0, 0), (-1, -1), 0.6, colors.HexColor("#D6DCE8")),
                               ("INNERGRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#D6DCE8")),
                               ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                               ("LEFTPADDING", (0, 0), (-1, -1), 9)]))
        elements += [t, Spacer(1, 5 * mm)]

    donnees = [feuille.colonnes] + [[Paragraph(str(c), s_cellule) for c in l] for l in feuille.lignes]
    if feuille.total:
        donnees.append([Paragraph(f"<b>{c}</b>", s_cellule) for c in feuille.total])
    if len(donnees) == 1:
        donnees.append([Paragraph("Aucune donnée sur la période", s_cellule)] + [""] * (len(feuille.colonnes) - 1))
    tableau = Table(donnees, repeatRows=1)
    style = [("BACKGROUND", (0, 0), (-1, 0), primaire), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
             ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"), ("FONTSIZE", (0, 0), (-1, 0), 8.5),
             ("LINEBELOW", (0, 1), (-1, -1), 0.4, colors.HexColor("#E3E8F2")),
             ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("TOPPADDING", (0, 0), (-1, -1), 4),
             ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]
    if feuille.total:
        style.append(("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#EEF1F8")))
    tableau.setStyle(TableStyle(style))
    elements.append(tableau)

    def pied(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.HexColor("#8A93A6"))
        canvas.drawString(14 * mm, 8 * mm, f"{organisation.sigle} · Document confidentiel — "
                                           f"édité le {datetime.now():%d/%m/%Y à %H:%M}")
        canvas.drawRightString(landscape(A4)[0] - 14 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(elements, onFirstPage=pied, onLaterPages=pied)
    return flux.getvalue()
