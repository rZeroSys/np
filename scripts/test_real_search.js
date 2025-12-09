#!/usr/bin/env node
/**
 * REAL JavaScript search test - runs the ACTUAL search logic
 */

const fs = require('fs');

// Load the actual generated JavaScript data
let content = fs.readFileSync('output/html/data/portfolio_cards.js', 'utf8');

// Replace 'const' with 'var' so eval works in this scope
content = content.replace('const PORTFOLIO_CARDS', 'var PORTFOLIO_CARDS');

// Execute it to get PORTFOLIO_CARDS
eval(content);

console.log(`Loaded ${PORTFOLIO_CARDS.length} portfolio cards\n`);

// Copy the EXACT globalSearch logic from the generated HTML
function globalSearch(query) {
    const globalQuery = query.toLowerCase().trim();

    if (!globalQuery) {
        return [];
    }

    const matches = [];
    PORTFOLIO_CARDS.forEach(p => {
        // Direct field matches
        const orgMatch = (p.org_name || '').toLowerCase().includes(globalQuery);
        const displayMatch = (p.display_name || '').toLowerCase().includes(globalQuery);
        const tenantMatch = (p.tenants || []).some(t => t.toLowerCase().includes(globalQuery));
        const subOrgMatch = (p.tenant_sub_orgs || []).some(s => s.toLowerCase().includes(globalQuery));
        const ownerMatch = (p.owners || []).some(o => o.toLowerCase().includes(globalQuery));
        const managerMatch = (p.managers || []).some(m => m.toLowerCase().includes(globalQuery));

        // NEW: Check search_aliases (CSV-defined aliases like 'Cal', 'USC', 'MIT', 'NYC')
        const aliasMatch = (p.search_aliases || []).some(alias => {
            const a = alias.toLowerCase();
            // Match if query contains alias OR alias contains query
            return a.includes(globalQuery) || globalQuery.includes(a) || a === globalQuery;
        });

        if (orgMatch || displayMatch || tenantMatch || subOrgMatch || ownerMatch || managerMatch || aliasMatch) {
            matches.push({
                name: p.org_name,
                display: p.display_name,
                aliases: p.search_aliases || []
            });
        }
    });

    return matches;
}

// TEST CASES - the ones user specifically asked for
const tests = [
    ['cal', 'University of California'],
    ['cal', 'California State University'],
    ['usc', 'University Of Southern California'],
    ['u of c', 'University of California'],
    ['u of c', 'University Of Chicago'],
    ['mit', 'Massachusetts Institute Of Technology'],
    ['ucla', 'University of California'],
    ['nyc', 'City Of New York'],
    ['la', 'City Of Los Angeles'],
    ['dc', 'District Of Columbia'],
    ['jll', 'Jones Lang LaSalle (JLL)'],
    ['cbre', 'CBRE Group (CBRE)'],
    ['gsa', 'General Services Administration (GSA)'],
    ['trojans', 'University Of Southern California'],
    ['cal state', 'California State University'],
    ['harvard', 'Harvard University'],
    ['stanford', 'Stanford University'],
    ['nyu', 'New York University'],
    ['boston', 'City Of Boston'],
    ['seattle', 'City Of Seattle'],
    ['chicago', 'City Of Chicago'],
    ['marriott', 'Marriott'],
    ['hilton', 'Hilton'],
    ['walmart', 'Walmart'],
    ['target', 'Target'],
    ['costco', 'Costco'],
    ['kaiser', 'Kaiser Permanente'],
];

console.log('='.repeat(70));
console.log('REAL JAVASCRIPT SEARCH TEST (using actual generated data)');
console.log('='.repeat(70));
console.log('');

let passed = 0;
let failed = 0;

tests.forEach(([query, expected]) => {
    const results = globalSearch(query);
    const resultNames = results.map(r => r.name);
    const found = resultNames.some(r => r.toLowerCase().includes(expected.toLowerCase()));

    if (found) {
        console.log(`✅ PASS | '${query}' → found '${expected}'`);
        passed++;
    } else {
        console.log(`❌ FAIL | '${query}' → expected '${expected}'`);
        console.log(`         Got ${results.length} results: ${resultNames.slice(0,5).join(', ')}...`);
        failed++;
    }
});

console.log('');
console.log('='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed out of ${tests.length} tests`);
console.log('='.repeat(70));

if (failed > 0) {
    console.log('\n❌ SOME TESTS FAILED!');
    process.exit(1);
} else {
    console.log('\n✅ ALL TESTS PASSED!');
}
