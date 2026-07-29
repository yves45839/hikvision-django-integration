# LR Time — Application mobile employé

Application mobile (Expo / React Native, TypeScript) permettant aux employés de
pointer leur arrivée et leur départ par géolocalisation, de consulter leur
planning du jour et leur historique de pointages.

> ⚠️ **Avertissement important** : « Le contrôle GPS est un contrôle de
> proximité, pas une preuve antifraude de présence. » Un téléphone peut
> simuler sa position (mock location). L'application transmet l'indicateur
> `mocked` au backend, mais le pointage GPS ne doit pas être considéré comme
> une preuve juridique de présence sur site.

## Prérequis

- **Node.js** ≥ 18 (LTS recommandé) et npm
- **Expo Go** installé sur le téléphone de test
  ([Android](https://play.google.com/store/apps/details?id=host.exp.exponent) /
  [iOS](https://apps.apple.com/app/expo-go/id982107779))
- Le backend Django LR Time démarré et accessible **sur le même réseau
  Wi-Fi** que le téléphone
- (Pour les builds de production) un compte [Expo / EAS](https://expo.dev)

## Installation

```bash
cd mobile
npm install
```

## Configuration

Copier le fichier d'exemple et renseigner l'URL du backend :

```bash
cp .env.example .env
```

```env
# IP LAN de la machine qui fait tourner le backend de dev
# (PAS localhost : le téléphone doit pouvoir joindre cette adresse)
EXPO_PUBLIC_API_BASE_URL=http://192.168.1.10:8000
```

Pour trouver l'IP LAN de votre machine : `ipconfig` (Windows) ou
`ip addr` / `ifconfig` (Linux/macOS). Vérifier que le backend écoute bien sur
`0.0.0.0:8000` (`python manage.py runserver 0.0.0.0:8000`) et que le pare-feu
autorise le port 8000.

## Lancement en développement

```bash
npx expo start
```

Puis scanner le QR code affiché avec **Expo Go** (Android : depuis
l'application ; iOS : depuis l'appareil photo). Le téléphone et l'ordinateur
doivent être sur le même réseau local.

Commandes utiles :

| Commande | Effet |
| --- | --- |
| `npx expo start` | Démarre le serveur de dev (QR code Expo Go) |
| `npx expo start --tunnel` | Mode tunnel si le LAN bloque les connexions directes |
| `npm run typecheck` | Vérification TypeScript (`tsc --noEmit`) |

### Lien d'invitation (deep link)

L'application gère le schéma `lrtime://accept-invitation?token=<secret>`.
En développement avec Expo Go, tester avec :

```bash
npx uri-scheme open "exp://<ip-metro>:8081/--/accept-invitation?token=XXX" --android
```

L'employé peut aussi coller son code d'invitation manuellement depuis l'écran
« J'ai un code d'invitation ».

### Notifications push

Les notifications push Expo nécessitent un **projet EAS** (`projectId`) et ne
fonctionnent pas dans un simulateur. En développement sans projet EAS,
l'enregistrement du token échoue silencieusement — le reste de l'application
fonctionne normalement.

## Builds de production (EAS)

Vue d'ensemble :

```bash
npm install -g eas-cli
eas login
eas build:configure          # génère eas.json et le projectId
eas build --platform android # AAB pour Google Play
eas build --platform ios     # IPA pour l'App Store
eas submit                   # envoi vers les stores
```

Les identifiants applicatifs sont déjà configurés dans `app.json` :
`com.labelci.lrtime` (Android et iOS), schéma `lrtime`.

### Prérequis de publication sur les stores (à la charge du client)

- **Google Play** : compte développeur Google Play — **25 $ (paiement
  unique)**. Prévoir la fiche store (icône, captures, politique de
  confidentialité) et la déclaration d'usage de la localisation.
- **Apple App Store** : compte Apple Developer Program — **99 $/an**.
  Prévoir la justification de l'usage de la localisation
  (`NSLocationWhenInUseUsageDescription`, déjà renseignée FR+EN) et le
  passage en revue Apple (délai de quelques jours).

## Architecture rapide

```
mobile/
├── app/                     # Écrans (expo-router)
│   ├── _layout.tsx          # Providers i18n + session, garde d'authentification
│   ├── login.tsx            # Connexion (identifiant + mot de passe)
│   ├── accept-invitation.tsx# Activation de compte par code d'invitation
│   └── (tabs)/
│       ├── index.tsx        # Écran principal « Pointer » (GPS + planning)
│       ├── history.tsx      # Historique groupé par jour
│       └── settings.tsx     # Langue, compte, version, déconnexion
└── src/
    ├── api/                 # client.ts (JWT + refresh rotatif), auth.ts, mobile.ts
    ├── auth/                # Contexte de session
    ├── components/          # Composants UI (styles RN simples, sans UI kit)
    ├── i18n/                # FR/EN (deux dictionnaires typés, choix persisté)
    ├── lib/                 # thème, installation_id, UUID
    └── notifications.ts     # Push Expo (enregistrement + tap → accueil)
```

Points notables :

- **Jetons** : access token en mémoire uniquement ; refresh token dans le
  stockage sécurisé (`expo-secure-store`). La **rotation des refresh tokens**
  est activée côté serveur : le nouveau refresh token est persisté
  immédiatement après chaque rafraîchissement.
- **Idempotence des pointages** : chaque tentative génère une
  `idempotency_key` (UUID) conservée tant que le serveur n'a pas répondu —
  un nouvel essai après une coupure réseau ne peut pas créer de doublon.
- **Précision GPS** : première mesure en précision « Balanced » ; si la
  précision dépasse 150 m, nouvelle mesure automatique en « High ». En cas
  d'erreur `ACCURACY_TOO_LOW` du serveur, un bouton « Réessayer en haute
  précision » est proposé.
