/* global window */

/* The 8 employees from the screenshot, plus a few extras
   so the table isn't too sparse. Identifier columns:
   face, card, bt (bluetooth), fp (fingerprint), badge.
*/
window.INITIAL_PEOPLE = [
  { id: '99',         first: 'test',    last: 'prenon',   dept: 'd-test',  ids: { face: 0, card: 1, bt: 0, fp: 0, badge: 0 } },
  { id: '5954522101', first: 'MIKE',    last: 'EHUI',     dept: 'd-root',  ids: { face: 0, card: 1, bt: 0, fp: 1, badge: 0 } },
  { id: '2',          first: 'No Name', last: '--',       dept: 'd-root',  empty: true, ids: { face: 0, card: 0, bt: 0, fp: 0, badge: 0 } },
  { id: '14',         first: 'via',     last: 'hikconnec', dept: 'd-root', ids: { face: 0, card: 1, bt: 0, fp: 1, badge: 0 } },
  { id: '178',        first: 'Aïcha',   last: 'BENALI',   dept: 'd-rh',     ids: { face: 1, card: 1, bt: 0, fp: 0, badge: 0 } },
  { id: '301',        first: 'Karim',   last: 'TAZI',     dept: 'd-prod-a', ids: { face: 1, card: 1, bt: 0, fp: 1, badge: 0 } },
  { id: '402',        first: 'Mehdi',   last: 'KABBAJ',   dept: 'd-prod-a', ids: { face: 0, card: 1, bt: 0, fp: 1, badge: 0 } },
  { id: '521',        first: 'Imane',   last: 'OUAZZANI', dept: 'd-rh',     ids: { face: 0, card: 0, bt: 0, fp: 0, badge: 0 } },
];

/* Department tree.
   - All departments have a color and an icon key (see I in icons.jsx).
   - children: array of dept ids (kept ordered for drag-reorder).
*/
window.INITIAL_DEPTS = {
  'd-root': { id: 'd-root', name: 'All Departments', icon: 'building', color: 'blue',   parent: null,    children: ['d-test', 'd-prod', 'd-rh', 'd-secu', 'd-maint'] },
  'd-test': { id: 'd-test', name: 'Test',            icon: 'folder',   color: 'slate',  parent: 'd-root', children: [] },
  'd-prod': { id: 'd-prod', name: 'Production',      icon: 'factory',  color: 'orange', parent: 'd-root', children: ['d-prod-a','d-prod-b'] },
  'd-prod-a': { id: 'd-prod-a', name: 'Hall A',      icon: 'folder',   color: 'orange', parent: 'd-prod', children: [] },
  'd-prod-b': { id: 'd-prod-b', name: 'Hall B',      icon: 'folder',   color: 'orange', parent: 'd-prod', children: [] },
  'd-rh':   { id: 'd-rh',   name: 'Ressources humaines', icon: 'users', color: 'pink',  parent: 'd-root', children: [] },
  'd-secu': { id: 'd-secu', name: 'Sécurité',        icon: 'shield',   color: 'green',  parent: 'd-root', children: [] },
  'd-maint': { id: 'd-maint', name: 'Maintenance',   icon: 'tools',    color: 'violet', parent: 'd-root', children: [] },
};

/* Color tokens for departments — backgrounds for the icon tile and chip.
   Each entry: { soft, fg, dot, bd, name }  (chip styling).
*/
window.DEPT_COLORS = {
  blue:   { soft: '#EEF4FF', fg: '#173FA1', dot: '#2F6BE6', bd: '#B7CCFF', label: 'Bleu' },
  orange: { soft: '#FFF6EC', fg: '#9A3F00', dot: '#F97316', bd: '#FFE6CC', label: 'Orange' },
  green:  { soft: '#ECFDF5', fg: '#047857', dot: '#10B981', bd: '#BBF7D0', label: 'Vert' },
  pink:   { soft: '#FCE7F3', fg: '#9D174D', dot: '#DB2777', bd: '#FBCFE8', label: 'Rose' },
  violet: { soft: '#EDE9FE', fg: '#5B21B6', dot: '#7C3AED', bd: '#DDD6FE', label: 'Violet' },
  amber:  { soft: '#FEF3C7', fg: '#92400E', dot: '#F59E0B', bd: '#FDE68A', label: 'Ambre' },
  teal:   { soft: '#CCFBF1', fg: '#115E59', dot: '#14B8A6', bd: '#99F6E4', label: 'Teal' },
  slate:  { soft: '#F1F5F9', fg: '#334155', dot: '#64748B', bd: '#CBD5E1', label: 'Ardoise' },
};

window.DEPT_ICONS = ['building','folder','factory','users','shield','briefcase','store','truck','tools'];
