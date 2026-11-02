"""Identité de l'entreprise cliente (marque blanche) : nom, logo, couleurs, politique de sécurité."""
import base64

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from server.app.database import get_db
from server.app.models import Organisation, Utilisateur
from server.app.schemas import OrganisationModification, OrganisationSortie
from server.app.securite import auditer, exiger_droit

router = APIRouter(prefix="/api/organisation", tags=["Organisation"])
TYPES_LOGO = {"image/png", "image/jpeg", "image/svg+xml", "image/webp"}


def organisation(db: Session) -> Organisation:
    org = db.query(Organisation).first()
    if org is None:
        org = Organisation()
        db.add(org)
        db.commit()
    return org


def organisation_sortie(org: Organisation) -> OrganisationSortie:
    sortie = OrganisationSortie.model_validate(org)
    sortie.a_un_logo = org.logo is not None
    return sortie


@router.get("", response_model=OrganisationSortie)
def lire(db: Session = Depends(get_db)):
    """Public : nécessaire à l'affichage de l'écran de connexion et des terminaux."""
    return organisation_sortie(organisation(db))


@router.get("/logo")
def logo(db: Session = Depends(get_db)):
    org = organisation(db)
    if org.logo is None:
        raise HTTPException(404, "Aucun logo")
    return Response(org.logo, media_type=org.logo_type, headers={"Cache-Control": "public, max-age=300"})


@router.put("", response_model=OrganisationSortie)
def modifier(donnees: OrganisationModification, request: Request,
             acteur: Utilisateur = Depends(exiger_droit("utilisateurs.gerer")), db: Session = Depends(get_db)):
    org = organisation(db)
    valeurs = donnees.model_dump(exclude_unset=True)
    for k, v in valeurs.items():
        setattr(org, k, v)
    auditer(db, acteur.identifiant, "MODIFICATION_ORGANISATION", ", ".join(sorted(valeurs)), request)
    db.commit()
    return organisation_sortie(org)


@router.post("/logo", response_model=OrganisationSortie)
def changer_logo(donnees: dict, request: Request, acteur: Utilisateur = Depends(exiger_droit("utilisateurs.gerer")),
                 db: Session = Depends(get_db)):
    """Corps : {"image": "data:image/png;base64,..."} (500 Ko maximum)."""
    image = str(donnees.get("image", ""))
    if not image.startswith("data:") or ";base64," not in image:
        raise HTTPException(400, "Format attendu : data-URL base64")
    entete, contenu = image.split(",", 1)
    type_mime = entete[5:].split(";")[0]
    if type_mime not in TYPES_LOGO:
        raise HTTPException(400, "Formats acceptés : PNG, JPEG, SVG, WebP")
    octets = base64.b64decode(contenu)
    if len(octets) > 500_000:
        raise HTTPException(400, "Logo trop volumineux (500 Ko maximum)")
    org = organisation(db)
    org.logo, org.logo_type = octets, type_mime
    auditer(db, acteur.identifiant, "MODIFICATION_LOGO", request=request)
    db.commit()
    return organisation_sortie(org)
