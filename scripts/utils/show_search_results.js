#!/usr/bin/env node
/**
 * Show actual search results for key queries
 */

const fs = require('fs');

let content = fs.readFileSync('output/html/data/portfolio_cards.js', 'utf8');
content = content.replace('const PORTFOLIO_CARDS', 'var PORTFOLIO_CARDS');
eval(content);

function globalSearch(query) {
    const globalQuery = query.toLowerCase().trim();
    if (!globalQuery) return [];

    const matches = [];
    PORTFOLIO_CARDS.forEach(p => {
        const orgMatch = (p.org_name || '').toLowerCase().includes(globalQuery);
        const displayMatch = (p.display_name || '').toLowerCase().includes(globalQuery);
        const tenantMatch = (p.tenants || []).some(t => t.toLowerCase().includes(globalQuery));
        const subOrgMatch = (p.tenant_sub_orgs || []).some(s => s.toLowerCase().includes(globalQuery));
        const ownerMatch = (p.owners || []).some(o => o.toLowerCase().includes(globalQuery));
        const managerMatch = (p.managers || []).some(m => m.toLowerCase().includes(globalQuery));
        const aliasMatch = (p.search_aliases || []).some(alias => {
            const a = alias.toLowerCase();
            return a.includes(globalQuery) || globalQuery.includes(a) || a === globalQuery;
        });

        if (orgMatch || displayMatch || tenantMatch || subOrgMatch || ownerMatch || managerMatch || aliasMatch) {
            matches.push({
                name: p.org_name,
                display: p.display_name,
                buildings: p.building_count,
                matchedVia: aliasMatch ? 'ALIAS' : 'direct'
            });
        }
    });

    return matches;
}

// Show results for key queries
const queries = ['cal', 'usc', 'u of c', 'mit', 'nyc', 'jll', 'gsa'];

console.log('='.repeat(70));
console.log('ACTUAL SEARCH RESULTS');
console.log('='.repeat(70));

queries.forEach(q => {
    const results = globalSearch(q);
    console.log(`\n🔍 Search: "${q}" → ${results.length} results`);
    console.log('-'.repeat(50));

    // Show top 5 results sorted by building count
    results
        .sort((a, b) => b.buildings - a.buildings)
        .slice(0, 5)
        .forEach((r, i) => {
            const marker = r.matchedVia === 'ALIAS' ? '⭐' : '  ';
            console.log(`  ${marker} ${r.display || r.name} (${r.buildings} buildings)`);
        });

    if (results.length > 5) {
        console.log(`  ... and ${results.length - 5} more`);
    }
});

console.log('\n' + '='.repeat(70));
console.log('⭐ = matched via search alias (not just direct text match)');
console.log('='.repeat(70));
