# Rapport d'audit — Interfaces frontend LR Time
**Date :** 2026-05-10  
**Périmètre :** Analyse statique exhaustive du code source Next.js (`v0-secure-point-dashboard-design`)  
**Interfaces auditées :** Connexion · Mot de passe oublié / Réinitialisation · Création d'employé · Création de quart · Extraction de rapport

---

## Légende de sévérité

| Niveau | Signification |
|--------|---------------|
| 🔴 Critique | Bloque l'utilisation ou cause une perte de données |
| 🟠 Majeur | Dégrade significativement l'expérience ou induit des erreurs fréquentes |
| 🟡 Mineur | Gêne légère, inconsistance ou manque de polish |

---

## 1. Page de connexion (`/login`)

**Fichier :** `app/login/page.tsx`

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| C1 | 🔴 | **Aucun bouton "afficher le mot de passe"** | Le champ `type="password"` ne propose pas de toggle œil pour révéler la saisie. Sur mobile, les risques de faute de frappe sont élevés et l'utilisateur n'a aucun moyen de vérifier ce qu'il tape. |
| C2 | 🟠 | **Aucune validation du format email** | La fonction `handleSubmit` vérifie uniquement que le champ `identifier` n'est pas vide (`!identifier.trim()`). Une saisie du type `"abc"` ou `"123"` passe sans erreur. |
| C3 | 🟠 | **Absence de limite de tentatives ou feedback de sécurité** | Pas d'indication à l'utilisateur après N échecs consécutifs (ni délai, ni suggestion de "mot de passe oublié", ni CAPTCHA). Le message d'erreur générique `"Connexion impossible."` ne guide pas l'utilisateur. |
| C4 | 🟠 | **Pas de case "se souvenir de moi"** | La session expire sans que l'utilisateur puisse contrôler la durée. Pas de checkbox `remember_me` dans le formulaire ni dans l'appel `loginWithCredentials`. |
| C5 | 🟡 | **Placeholder révèle l'email interne** | `placeholder="noreply@label-ci.com"` expose l'adresse email de l'entreprise. Utiliser un exemple neutre tel que `"prenom.nom@societe.com"`. |
| C6 | 🟡 | **Faute typographique** | `"Creer un compte"` (lien vers `/signup`) — accent manquant : devrait être `"Créer un compte"`. |
| C7 | 🟡 | **Pas de gestion du mode "caps lock activé"** | Aucune détection ni avertissement quand le verrou majuscules est actif, source fréquente d'échec de connexion. |

---

## 2. Mot de passe oublié (`/auth/forgot-password`)

**Fichier :** `app/auth/forgot-password/page.tsx`

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| F1 | 🔴 | **Aucun choix de méthode de réception** | La description annonce _"recevez un lien ou un code OTP"_ mais le formulaire n'offre aucun moyen de choisir. L'utilisateur ne sait pas ce qu'il va recevoir. |
| F2 | 🟠 | **Aucune validation du format email** | Le champ `identifier` n'est validé que sur la non-vacuité. Une saisie invalide est soumise à l'API sans filtre côté client. |
| F3 | 🟠 | **Redirection post-succès inconditionnelle vers `/auth/reset-password`** | Après confirmation, un bouton _"Réinitialiser mon mot de passe"_ s'affiche immédiatement. L'utilisateur est redirigé avant d'avoir reçu son email/OTP. Il atterrit sur un formulaire de token qu'il ne possède pas encore. |
| F4 | 🟠 | **Pas d'indication du délai d'expiration du lien/code** | L'API renvoie un `expires_at` (visible dans `PasswordResetRequestResponse`) mais la page ne l'affiche jamais. L'utilisateur ne sait pas combien de temps il a. |
| F5 | 🟡 | **Faute d'accent** | Toast `"Echec de la demande"` → devrait être `"Échec de la demande"`. |
| F6 | 🟡 | **Pas de bouton "Retour" visible pendant la saisie** | Aucun lien vers `/login` n'est affiché avant la soumission du formulaire (uniquement après succès). |

---

## 3. Réinitialisation du mot de passe (`/auth/reset-password`)

**Fichier :** `app/auth/reset-password/page.tsx`

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| R1 | 🔴 | **Formulaire cognitif trop chargé — tous les champs affichés simultanément** | Token + Email + OTP + Nouveau mot de passe + Confirmation sont tous visibles en même temps. L'utilisateur qui a reçu un lien ne comprend pas pourquoi il y a aussi des champs Email/OTP (et vice-versa). Un wizard conditionnel s'impose : détecter la présence du token dans l'URL (`?token=...`) et n'afficher que les champs pertinents. |
| R2 | 🟠 | **Aucun indicateur de force du mot de passe** | La seule règle affichée/vérifiée est la longueur minimale de 8 caractères. Pas de jauge, pas d'indication sur majuscules/chiffres/caractères spéciaux. |
| R3 | 🟠 | **Aucun bouton "afficher le mot de passe"** | Même problème que C1. Les deux champs `newPassword` et `confirmPassword` sont en `type="password"` sans toggle de visibilité. |
| R4 | 🟠 | **Champ OTP sans clavier numérique sur mobile** | `inputMode` n'est pas défini sur le champ OTP. Sur mobile, le clavier alphanumérique s'ouvre au lieu du clavier numérique. Ajouter `inputMode="numeric"` et `pattern="[0-9]*"`. |
| R5 | 🟡 | **Validation de la confirmation du mot de passe différée** | L'erreur `"Les mots de passe ne correspondent pas"` n'apparaît qu'à la soumission. Un retour immédiat `onBlur` sur le champ de confirmation améliorerait l'expérience. |
| R6 | 🟡 | **Faute d'accent** | Toast `"Echec de réinitialisation"` → `"Échec de réinitialisation"`. |

---

## 4. Création d'un employé (`/employees` → modal `AddEmployeeModal`)

**Fichier :** `components/employees/add-employee-modal.tsx`

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| E1 | 🔴 | **Champ téléphone sans aucune validation** | Le champ `phone` accepte n'importe quelle chaîne de caractères. Pas de format, pas de regex, pas de `maxLength`. La valeur est envoyée telle quelle à l'API. |
| E2 | 🔴 | **Aucun avertissement si fermeture avec données non sauvegardées** | Fermer le modal (`onOpenChange(false)`) réinitialise silencieusement tous les champs saisis. Aucune dialog de confirmation `"Voulez-vous vraiment annuler ?"` n'est proposée. |
| E3 | 🟠 | **Champ `employeeNo` sans validation de format ni de longueur** | Vérifié uniquement sur non-vacuité. Pas de `maxLength`, pas de règle de format (alphanumérique, tirets autorisés ?). L'employé peut recevoir un ID avec des espaces ou des caractères spéciaux. |
| E4 | 🟠 | **Champ `name` sans vérification de doublon** | L'unicité du numéro de carte est vérifiée (lignes 489-494) mais pas le nom. Deux employés peuvent avoir exactement le même nom sans avertissement. |
| E5 | 🟠 | **Upload photo : aucune restriction de type ni de taille** | `handlePhotoUpload` accepte n'importe quel fichier. Un fichier de 50 Mo ou un `.pdf` sera soumis à l'API sans filtre. Ajouter `accept="image/jpeg,image/png,image/webp"` et une vérification de `file.size`. |
| E6 | 🟠 | **L'enrôlement biométrique n'est possible qu'après la création** | `handleCaptureFingerprint` vérifie `!isEditing || !employeeToEdit?.apiId` et affiche `"Enrôlement disponible uniquement après création de l'employé."` — mais ce message apparaît seulement dans la console d'erreur locale, pas assez mis en avant dans l'interface. L'utilisateur du modal de création ne voit pas d'emblée que l'onglet Biométrie ne fonctionnera pas pendant cette étape. |
| E7 | 🟠 | **Aucun `maxLength` sur les champs texte libres** | `name`, `position`, `email`, `phone`, `cardNumber` n'ont aucun attribut `maxLength`. Des saisies très longues ne sont pas bloquées côté client. |
| E8 | 🟡 | **Onglet actif non verrouillé sur les erreurs** | Si des erreurs existent dans l'onglet "Informations" et que l'utilisateur a navigué vers l'onglet "Biométrie", la soumission échoue mais l'onglet erroné n'est pas activé automatiquement. L'indicateur `hasInfoErrors` est calculé mais n'est pas utilisé pour rediriger l'onglet. |
| E9 | 🟡 | **Messages d'erreur sans accents** | `"L'ID employe est requis"`, `"Le departement est requis"`, `"Chaque doigt (finger index) doit etre unique."` → accents manquants systématiques. |
| E10 | 🟡 | **Champ `validityEnd` par défaut à +10 ans sans explication** | L'utilisateur ne comprend pas pourquoi la date de fin est préremplie à +10 ans. Aucun tooltip ni info-bulle. |

---

## 5. Création d'un quart de travail (`/planning` → dialog shift)

**Fichier :** `app/planning/page.tsx` (à partir de la ligne ~3442)

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| Q1 | 🔴 | **Aucune validation que l'heure de pause est comprise dans le créneau de service** | On vérifie uniquement que `break_start` et `break_end` sont au format HH:MM, mais pas qu'ils se situent entre `start_time` et `end_time`. Un utilisateur peut créer un quart 08h-17h avec une pause 20h-21h. |
| Q2 | 🔴 | **Aucune validation de durée minimale de quart** | Un quart `start_time=08:00` et `end_time=08:00` passe la validation (même heure). Un quart de 1 minute est également accepté. |
| Q3 | 🟠 | **Code d'erreur technique exposé à l'utilisateur** | Les erreurs affichent `"Code: SHIFT_BREAK_INCOMPLETE"` en rouge à l'écran (ligne 3457 : `<p>Code: {error.code}</p>`). Ce code interne ne devrait pas être visible pour un utilisateur non-technique. |
| Q4 | 🟠 | **Aucune indication que `end_time < start_time` signifie un quart de nuit** | Pour un quart de nuit 22h-06h, l'interface ne confirme pas ce comportement attendu. Un utilisateur peut croire qu'il a fait une erreur. Ajouter un badge `"Quart de nuit"` quand `end_time ≤ start_time`. |
| Q5 | 🟠 | **Champs de tolérance de retard (`late_allowable_minutes`) sans unité ni plage visibles** | L'étiquette ne précise pas `"en minutes"`. Pas de `min="0"` ni de `max` visible. Un utilisateur peut saisir `"999"` (16h40 de tolérance) sans avertissement. |
| Q6 | 🟠 | **Les heures supplémentaires ne valident pas la cohérence temporelle** | Si `overtime_start_time` est antérieur à `end_time`, aucune erreur n'est levée. La logique `minutesForward(endTime, overtimeEnd)` peut produire des valeurs négatives silencieusement. |
| Q7 | 🟡 | **Inputs de temps en `type="text"` au lieu de `type="time"`** | Tous les champs horaires utilisent `type="text"` avec `inputMode="numeric"`. `type="time"` apporterait un sélecteur natif sur mobile et une validation HTML5 automatique. |
| Q8 | 🟡 | **Titre du dialog sans accent** | `"Creer un quart de travail"` → `"Créer un quart de travail"`. Idem description : `"Ajoute un quart..."` → `"Ajoute un quart..."` (style impératif non standard, préférer infinitif). |
| Q9 | 🟡 | **Le champ `Code` (code court du quart) n'a aucune indication d'utilisation** | L'utilisateur ne sait pas à quoi sert ce code, quelle longueur est attendue, ni s'il doit être unique. |

---

## 6. Extraction de rapport (`/reports`)

**Fichier :** `app/reports/page.tsx`

| # | Sévérité | Insuffisance | Détail technique |
|---|----------|--------------|------------------|
| RP1 | 🔴 | **Aucune validation que `customStartDate ≤ customEndDate`** | Les deux inputs `type="date"` sont indépendants (lignes 1164-1178). L'utilisateur peut saisir `startDate=2026-05-10` et `endDate=2026-01-01`, puis lancer la génération du rapport sans aucun message d'erreur. L'API reçoit une plage invalide. |
| RP2 | 🔴 | **`localStorage` utilisé sans vérification de disponibilité robuste** | Les clés `EXPORT_FIELDS_STORAGE_KEY` et `EXPORT_VIEWS_STORAGE_KEY` sont accédées via `window.localStorage`. Si l'utilisateur a désactivé le stockage local (mode privé strict, certains navigateurs d'entreprise), l'état revient silencieusement aux valeurs par défaut à chaque chargement et les vues sauvegardées sont perdues. |
| RP3 | 🟠 | **Aucune limite de plage de dates pour l'export** | Avec `customRangeEnabled`, rien n'empêche de demander un rapport sur 5 ans. Ni avertissement, ni cap, ni estimation du volume. Risque de timeout ou de saturation mémoire côté client lors du téléchargement. |
| RP4 | 🟠 | **Boutons d'export (Excel/PDF/CSV) accessibles même quand aucun rapport n'est chargé** | `handleExport` est appelable avant que `report` soit défini. Aucun `disabled` conditionnel sur ces boutons. L'appel API échoue et affiche une erreur générique. |
| RP5 | 🟠 | **Nom de vue sauvegardée sans validation** | Il est possible de sauvegarder une vue avec un nom vide ou dupliqué. Aucune contrainte `if (!viewName.trim())` n'existe dans la logique de sauvegarde des vues d'export. |
| RP6 | 🟠 | **Le formulaire de correction de pointage ne préremplit pas la date courante** | Quand l'utilisateur ouvre le panneau de correction, `arrivalTime` et `departureTime` sont des chaînes vides. Aucune valeur issue de la ligne de tableau sélectionnée n'est utilisée comme point de départ. |
| RP7 | 🟡 | **Labels sans accents** | `"Departement"`, `"Employe"`, `"Entrees"`, `"Sorties"`, `"Ecart arrivee"`, `"Ecart depart"`, `"Arrivee attendue"`, `"Depart attendu"` → accents systématiquement absents dans la définition `ATTENDANCE_EXPORT_FIELDS`. |
| RP8 | 🟡 | **Plage personnalisée — champs dates sans labels accessibles** | Les deux `<Input type="date">` de la plage personnalisée ne possèdent ni `<Label>` associé, ni attribut `aria-label`. Ils sont séparés par une flèche `→` de type décoratif sans signification pour les lecteurs d'écran. |
| RP9 | 🟡 | **Sélecteur de colonnes d'export non groupé** | Les 22 champs d'export sont listés à plat sans regroupement sémantique (identité, horaires, écarts, événements…). La liste est difficile à parcourir. |

---

## 7. Problèmes transversaux

| # | Sévérité | Insuffisance | Interfaces concernées |
|---|----------|--------------|----------------------|
| T1 | 🔴 | **Absence systématique de dialog de confirmation avant destruction** | Suppression d'un employé (`deleteEmployee`), suppression d'un quart (`deleteWorkShift`), suppression d'un planning : aucune confirmation n'est demandée. Un clic malencontreux est irréversible. | Employés, Planning |
| T2 | 🟠 | **Accents manquants systématiques** | Des dizaines de chaînes UI sont dépourvues d'accents (é, è, ê, à, ô…) dans les labels, placeholders, messages d'erreur et titres. Cela nuit à la crédibilité du produit sur le marché francophone. | Toutes |
| T3 | 🟠 | **Aucune gestion du token expiré en cours de session** | Si le jeton d'accès expire pendant que l'utilisateur est sur une page (rapport en cours, modal ouverte), l'erreur API est affichée comme une erreur générique sans redirection vers `/login`. | Toutes |
| T4 | 🟠 | **Pas de feedback de chargement initial des pages protégées** | Les pages `employees`, `planning`, `reports` chargent leurs données via `useEffect` sans état de skeleton global. En cas de latence réseau, l'utilisateur voit une page vide sans indication de chargement. | Employés, Planning, Rapports |
| T5 | 🟡 | **`NEXT_PUBLIC_EMPLOYEE_TENANT_CODE` hardcodé en fallback** | `const EMPLOYEE_TENANT_CODE = process.env.NEXT_PUBLIC_EMPLOYEE_TENANT_CODE ?? "HQ-CASA"` — si la variable d'environnement n'est pas définie, le code `"HQ-CASA"` est utilisé en production sans avertissement. | Planning, Rapports |
| T6 | 🟡 | **Aucune page 404 / état d'erreur pour les routes inexistantes** | `not-found.tsx` existe mais son contenu et son design n'ont pas été vérifiés pour cohérence avec la charte. | Global |

---

## Synthèse — Priorités de correction

| Priorité | Items | Impact |
|----------|-------|--------|
| **P1 — Immédiat** | C1, C2, R1, Q1, Q2, RP1, T1 | Erreurs de données, perte de travail, UX bloquante |
| **P2 — Court terme** | F1, F3, E1, E2, Q3, Q4, RP3, RP4, T2, T3 | Confusion utilisateur, données invalides en base |
| **P3 — Moyen terme** | Tous les 🟡 | Polish, accessibilité, crédibilité produit |

---

*Rapport généré par analyse statique du code source — `v0-secure-point-dashboard-design` — LR Time / Label Retail*
