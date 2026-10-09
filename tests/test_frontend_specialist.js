const fs = require('fs');
const assert = require('assert');

// 1. Check index.html
const html = fs.readFileSync('web/index.html', 'utf8');
assert(html.includes('export-dossier-button'), 'Missing export-dossier-button in index.html');
assert(html.includes('Ekspor Dokumen Debrief (Dossier)'), 'Missing label Ekspor Dokumen Debrief (Dossier) in index.html');
assert(html.includes('id="feedback-modal"'), 'Missing #feedback-modal in index.html');
assert(html.includes('id="star-modal"'), 'Missing #star-modal in index.html');
console.log('✓ index.html checks passed');

// 2. Check app.js
const appJs = fs.readFileSync('web/app.js', 'utf8');
assert(appJs.includes('candidate-feedback-btn'), 'Missing candidate-feedback-btn in app.js');
assert(appJs.includes('star-guide-btn'), 'Missing star-guide-btn in app.js');
assert(appJs.includes('/export/dossier'), 'Missing export dossier call in app.js');
assert(appJs.includes('/feedback'), 'Missing feedback API call in app.js');
assert(appJs.includes('/star-questions'), 'Missing star-questions API call in app.js');
assert(appJs.includes('openFeedbackModal'), 'Missing openFeedbackModal in app.js');
assert(appJs.includes('openStarModal'), 'Missing openStarModal in app.js');
console.log('✓ app.js checks passed');

// 3. Check app.css
const appCss = fs.readFileSync('web/app.css', 'utf8');
assert(appCss.includes('.feedback-modal'), 'Missing .feedback-modal styles in app.css');
assert(appCss.includes('.star-modal'), 'Missing .star-modal styles in app.css');
assert(appCss.includes('.feedback-card.strength'), 'Missing feedback strength styles in app.css');
assert(appCss.includes('.feedback-card.growth'), 'Missing feedback growth styles in app.css');
assert(appCss.includes('.star-quadrant-grid'), 'Missing star-quadrant-grid styles in app.css');
assert(appCss.includes('@media (max-width: 900px)'), 'Missing responsive tablet query in app.css');
console.log('✓ app.css checks passed');

console.log('ALL FRONTEND SPECIALIST VERIFICATIONS PASSED SUCCESSFULLY!');
