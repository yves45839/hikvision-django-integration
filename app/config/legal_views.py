"""
PHASE 6.1 — Pages légales (TOS, Privacy Policy)
"""
from django.http import JsonResponse


def terms_of_service(request):
    """Conditions Générales d'Utilisation"""
    return JsonResponse({
        "title": "Conditions Générales d'Utilisation",
        "version": "1.0",
        "effective_date": "2025-01-01",
        "content": """
Les présentes CGU régissent l'utilisation de SecurePoint, plateforme de gestion
d'accès multi-tenant alimentée par les équipements Hikvision.

1. ACCEPTATION DES TERMES
En utilisant cette plateforme, vous acceptez ces CGU. Si vous n'acceptez pas,
vous n'êtes pas autorisé à utiliser le service.

2. LICENCE D'UTILISATION
Nous vous accordons une licence limitée, non-exclusive et révocable pour utiliser
le service conformément à ces CGU.

3. CONDITIONS D'UTILISATION
Vous acceptez de ne pas :
- Contourner les mesures de sécurité
- Accéder aux données d'autres utilisateurs
- Mener des activités illégales
- Transmettre des malwares

4. LIMITATION DE RESPONSABILITÉ
Le service est fourni "tel quel". Nous déclinons toute responsabilité pour
les dégâts indirects, spéciaux ou punitifs.

5. MODIFICATION DES CGU
Nous pouvons modifier ces CGU. L'utilisation continue constitue l'acceptation.
"""
    })


def privacy_policy(request):
    """Politique de Confidentialité (RGPD-conforme)"""
    return JsonResponse({
        "title": "Politique de Confidentialité",
        "version": "1.0",
        "effective_date": "2025-01-01",
        "content": """
Nous collectons et traitons vos données conformément au RGPD (Règlement General
sur la Protection des Données) et aux lois applicables.

1. DONNEES COLLECTEES
- Données d'identification (nom, email, username)
- Données de profil (prénom, nom de famille)
- Données d'authentification (mot de passe haché, tokens)
- Données de journalisation (accès, IP, user-agent)
- Données biométriques (si applicable, chiffrées)

2. FONDEMENT LEGAL
- Consentement explicite pour le traitement
- Intérêt légitime pour la sécurité et le maintien du service
- Obligation légale (conservation de logs pour audit)

3. DUREE DE CONSERVATION
- Données utilisateur : pendant la durée du compte + 1 an après suppression
- Logs d'accès : 90 jours par défaut (configurable)
- Données biométriques : immédiatement après traitement si non stockées

4. DROITS DE L'UTILISATEUR
Vous avez le droit de :
- Accéder à vos données (art. 15)
- Rectifier vos données (art. 16)
- Vous opposer au traitement (art. 21)
- Demander l'effacement (art. 17 - "droit à l'oubli")
- Portabilité des données (art. 20)
- Demander une limitation (art. 18)

5. CONTACT POUR LES DROITS PRIVACY
support@label-ci.com

6. PARTAGE DES DONNEES
Vos données ne sont partagées que avec :
- Prestataires de service (authentification, hébergement)
- Autorités légales si requis par la loi
Aucune vente de données à des tiers.
"""
    })
