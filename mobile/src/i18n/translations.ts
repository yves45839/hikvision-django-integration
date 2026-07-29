/**
 * Two-dictionary i18n pattern. English is the reference dictionary;
 * `fr: typeof en` guarantees at compile time that no key is missing.
 * Interpolation uses {placeholders}, replaced by I18nProvider.t().
 */
export const en = {
  // Common
  'common.appName': 'LR Time',
  'common.loading': 'Loading…',
  'common.retry': 'Retry',
  'common.cancel': 'Cancel',
  'common.ok': 'OK',
  'common.genericError': 'Something went wrong. Please try again.',
  'common.networkError': 'Network error. Check your connection and try again.',
  'common.sessionExpired': 'Your session has expired. Please sign in again.',

  // Login
  'login.title': 'Sign in',
  'login.subtitle': 'Employee time tracking',
  'login.identifier': 'Email or username',
  'login.password': 'Password',
  'login.submit': 'Sign in',
  'login.submitting': 'Signing in…',
  'login.invitationLink': 'I have an invitation code',
  'login.invalidCredentials': 'Incorrect email/username or password.',
  'login.missingFields': 'Please enter your identifier and password.',

  // Invitation
  'invitation.title': 'Activate my account',
  'invitation.subtitle': 'Enter the invitation code you received to create your password.',
  'invitation.tokenLabel': 'Invitation code',
  'invitation.tokenPlaceholder': 'Paste your invitation code',
  'invitation.check': 'Check code',
  'invitation.checking': 'Checking…',
  'invitation.previewEmployee': 'Account for {name}',
  'invitation.previewTenant': 'Company: {tenant}',
  'invitation.previewEmail': 'Email: {email}',
  'invitation.previewExpires': 'Valid until {date}',
  'invitation.password': 'Choose a password',
  'invitation.confirmPassword': 'Confirm password',
  'invitation.passwordMismatch': 'Passwords do not match.',
  'invitation.submit': 'Activate and sign in',
  'invitation.submitting': 'Activating…',
  'invitation.backToLogin': 'Back to sign in',
  'invitation.error.INVALID_TOKEN': 'This invitation code is invalid.',
  'invitation.error.EXPIRED': 'This invitation has expired. Ask your manager for a new one.',
  'invitation.error.ALREADY_LINKED': 'This invitation has already been used. Try signing in instead.',
  'invitation.error.WEAK_PASSWORD': 'This password is too weak. Use at least 8 characters, avoid common words.',
  'invitation.error.EMAIL_IN_USE': 'An account already exists with this email. Try signing in instead.',

  // Tabs
  'tabs.home': 'Clock',
  'tabs.history': 'History',
  'tabs.settings': 'Settings',

  // Home
  'home.greeting': 'Hello {name}',
  'home.today': 'Today',
  'home.scheduleTitle': "Today's schedule",
  'home.restDay': 'Rest day — no work scheduled.',
  'home.noSchedule': 'No schedule defined for today.',
  'home.slotRest': 'Break',
  'home.punchesTitle': "Today's punches",
  'home.noPunches': 'No punches yet today.',
  'home.actionCheckIn': 'Clock in',
  'home.actionCheckOut': 'Clock out',
  'home.locating': 'Getting your location…',
  'home.sending': 'Sending…',
  'home.successCheckIn': 'Clocked in',
  'home.successCheckOut': 'Clocked out',
  'home.successAtSite': 'at {site}',
  'home.successDistance': '{distance} m from site',
  'home.zoneBorderline': 'At the edge of the authorized zone',
  'home.scheduleOnTime': 'Within scheduled hours',
  'home.scheduleEarly': '{minutes} min early',
  'home.scheduleLate': '{minutes} min late',
  'home.scheduleOutside': 'Outside scheduled hours',
  'home.error.OUT_OF_ZONE': 'You are {distance} m away from {site}, allowed {tolerance} m.',
  'home.error.TOO_SOON': 'Punch already recorded. Please wait {seconds}s before trying again.',
  'home.error.ACCURACY_TOO_LOW': 'GPS signal too imprecise (required: better than {max} m). Move away from buildings and try again.',
  'home.error.SUGGESTED_ACTION_CHANGED': 'Your status has changed in the meantime. The button has been updated — please check and try again.',
  'home.error.NO_SITE_CONFIGURED': 'No work site is configured for your company yet. Contact your manager.',
  'home.error.PROFILE_NOT_LINKED': 'Your account is not linked to an employee profile. Contact your manager.',
  'home.error.INVALID_COORDINATES': 'Invalid GPS coordinates were received. Please try again.',
  'home.error.locationDenied': 'Location permission is required to clock in/out. Please enable it in your phone settings.',
  'home.error.locationUnavailable': 'Could not get your location. Make sure GPS is enabled and try again.',
  'home.retryHighAccuracy': 'Retry with high accuracy',
  'home.dismiss': 'Dismiss',

  // History
  'history.title': 'History',
  'history.empty': 'No punches recorded yet.',
  'history.checkIn': 'Clock-in',
  'history.checkOut': 'Clock-out',
  'history.sourceMobile': 'Mobile',

  // Settings
  'settings.title': 'Settings',
  'settings.language': 'Language',
  'settings.english': 'English',
  'settings.french': 'Français',
  'settings.account': 'Account',
  'settings.employeeNo': 'Employee no.',
  'settings.company': 'Company',
  'settings.about': 'About',
  'settings.version': 'App version',
  'settings.logout': 'Sign out',
  'settings.loggingOut': 'Signing out…',
  'settings.gpsNotice':
    'GPS check is a proximity check, not tamper-proof evidence of presence.',
};

export const fr: typeof en = {
  // Commun
  'common.appName': 'LR Time',
  'common.loading': 'Chargement…',
  'common.retry': 'Réessayer',
  'common.cancel': 'Annuler',
  'common.ok': 'OK',
  'common.genericError': 'Une erreur est survenue. Veuillez réessayer.',
  'common.networkError': 'Erreur réseau. Vérifiez votre connexion et réessayez.',
  'common.sessionExpired': 'Votre session a expiré. Veuillez vous reconnecter.',

  // Connexion
  'login.title': 'Connexion',
  'login.subtitle': 'Pointage des employés',
  'login.identifier': 'Email ou identifiant',
  'login.password': 'Mot de passe',
  'login.submit': 'Se connecter',
  'login.submitting': 'Connexion…',
  'login.invitationLink': "J'ai un code d'invitation",
  'login.invalidCredentials': 'Identifiant ou mot de passe incorrect.',
  'login.missingFields': 'Veuillez saisir votre identifiant et votre mot de passe.',

  // Invitation
  'invitation.title': 'Activer mon compte',
  'invitation.subtitle':
    "Saisissez le code d'invitation reçu pour créer votre mot de passe.",
  'invitation.tokenLabel': "Code d'invitation",
  'invitation.tokenPlaceholder': "Collez votre code d'invitation",
  'invitation.check': 'Vérifier le code',
  'invitation.checking': 'Vérification…',
  'invitation.previewEmployee': 'Compte pour {name}',
  'invitation.previewTenant': 'Entreprise : {tenant}',
  'invitation.previewEmail': 'Email : {email}',
  'invitation.previewExpires': "Valable jusqu'au {date}",
  'invitation.password': 'Choisissez un mot de passe',
  'invitation.confirmPassword': 'Confirmez le mot de passe',
  'invitation.passwordMismatch': 'Les mots de passe ne correspondent pas.',
  'invitation.submit': 'Activer et se connecter',
  'invitation.submitting': 'Activation…',
  'invitation.backToLogin': 'Retour à la connexion',
  'invitation.error.INVALID_TOKEN': "Ce code d'invitation est invalide.",
  'invitation.error.EXPIRED':
    'Cette invitation a expiré. Demandez-en une nouvelle à votre responsable.',
  'invitation.error.ALREADY_LINKED':
    'Cette invitation a déjà été utilisée. Essayez de vous connecter.',
  'invitation.error.WEAK_PASSWORD':
    'Ce mot de passe est trop faible. Utilisez au moins 8 caractères, évitez les mots courants.',
  'invitation.error.EMAIL_IN_USE':
    'Un compte existe déjà avec cet email. Essayez de vous connecter.',

  // Onglets
  'tabs.home': 'Pointer',
  'tabs.history': 'Historique',
  'tabs.settings': 'Réglages',

  // Accueil
  'home.greeting': 'Bonjour {name}',
  'home.today': "Aujourd'hui",
  'home.scheduleTitle': "Planning du jour",
  'home.restDay': 'Jour de repos — aucun travail prévu.',
  'home.noSchedule': "Aucun planning défini pour aujourd'hui.",
  'home.slotRest': 'Pause',
  'home.punchesTitle': 'Pointages du jour',
  'home.noPunches': "Aucun pointage pour l'instant aujourd'hui.",
  'home.actionCheckIn': "Pointer l'arrivée",
  'home.actionCheckOut': 'Pointer le départ',
  'home.locating': 'Recherche de votre position…',
  'home.sending': 'Envoi…',
  'home.successCheckIn': 'Arrivée enregistrée',
  'home.successCheckOut': 'Départ enregistré',
  'home.successAtSite': 'à {site}',
  'home.successDistance': '{distance} m du site',
  'home.zoneBorderline': 'En limite de la zone autorisée',
  'home.scheduleOnTime': 'Dans les horaires prévus',
  'home.scheduleEarly': '{minutes} min en avance',
  'home.scheduleLate': '{minutes} min en retard',
  'home.scheduleOutside': 'Hors des horaires prévus',
  'home.error.OUT_OF_ZONE':
    'Vous êtes à {distance} m de {site}, distance autorisée : {tolerance} m.',
  'home.error.TOO_SOON':
    'Pointage déjà enregistré. Merci de patienter {seconds}s avant de réessayer.',
  'home.error.ACCURACY_TOO_LOW':
    'Signal GPS trop imprécis (requis : mieux que {max} m). Éloignez-vous des bâtiments et réessayez.',
  'home.error.SUGGESTED_ACTION_CHANGED':
    'Votre statut a changé entre-temps. Le bouton a été mis à jour — vérifiez puis réessayez.',
  'home.error.NO_SITE_CONFIGURED':
    "Aucun site de travail n'est configuré pour votre entreprise. Contactez votre responsable.",
  'home.error.PROFILE_NOT_LINKED':
    "Votre compte n'est pas relié à une fiche employé. Contactez votre responsable.",
  'home.error.INVALID_COORDINATES':
    'Coordonnées GPS invalides. Veuillez réessayer.',
  'home.error.locationDenied':
    "L'autorisation de localisation est nécessaire pour pointer. Activez-la dans les réglages de votre téléphone.",
  'home.error.locationUnavailable':
    "Impossible d'obtenir votre position. Vérifiez que le GPS est activé puis réessayez.",
  'home.retryHighAccuracy': 'Réessayer en haute précision',
  'home.dismiss': 'Fermer',

  // Historique
  'history.title': 'Historique',
  'history.empty': 'Aucun pointage enregistré pour le moment.',
  'history.checkIn': 'Arrivée',
  'history.checkOut': 'Départ',
  'history.sourceMobile': 'Mobile',

  // Réglages
  'settings.title': 'Réglages',
  'settings.language': 'Langue',
  'settings.english': 'English',
  'settings.french': 'Français',
  'settings.account': 'Compte',
  'settings.employeeNo': 'Matricule',
  'settings.company': 'Entreprise',
  'settings.about': 'À propos',
  'settings.version': "Version de l'application",
  'settings.logout': 'Se déconnecter',
  'settings.loggingOut': 'Déconnexion…',
  'settings.gpsNotice':
    "Le contrôle GPS est un contrôle de proximité, pas une preuve antifraude de présence.",
};

export type TranslationKey = keyof typeof en;
export type Lang = 'en' | 'fr';

export const dictionaries: Record<Lang, typeof en> = { en, fr };
