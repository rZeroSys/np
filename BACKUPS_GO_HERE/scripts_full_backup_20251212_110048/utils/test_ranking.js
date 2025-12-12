#!/usr/bin/env node
/**
 * Test search RANKING for conflicting terms
 */

const fs = require('fs');

let content = fs.readFileSync('output/html/data/portfolio_cards.js', 'utf8');
content = content.replace('const PORTFOLIO_CARDS', 'var PORTFOLIO_CARDS');
eval(content);

// Copy the NEW ranking search from generated HTML
function globalSearch(query) {
    const globalQuery = query.toLowerCase().trim();

    if (!globalQuery) return [];

    const scored = [];

    PORTFOLIO_CARDS.forEach(p => {
        let score = 0;
        const orgLower = (p.org_name || '').toLowerCase();
        const displayLower = (p.display_name || '').toLowerCase();

        // EXACT alias match (highest priority)
        const exactAliasMatch = (p.search_aliases || []).some(a => a.toLowerCase() === globalQuery);
        if (exactAliasMatch) score += 1000;

        // EXACT display_name match
        if (displayLower === globalQuery) score += 900;

        // Display name STARTS with query
        if (displayLower.startsWith(globalQuery)) score += 800;

        // Alias starts with query
        const aliasStartsWith = (p.search_aliases || []).some(a => a.toLowerCase().startsWith(globalQuery));
        if (aliasStartsWith) score += 700;

        // Alias contains query exactly as word
        const aliasContainsWord = (p.search_aliases || []).some(a => {
            const words = a.toLowerCase().split(/\s+/);
            return words.includes(globalQuery);
        });
        if (aliasContainsWord) score += 600;

        // Org name contains query
        if (orgLower.includes(globalQuery)) score += 300;

        // Display name contains query
        if (displayLower.includes(globalQuery)) score += 250;

        // Alias contains query (partial)
        const aliasContains = (p.search_aliases || []).some(a => a.toLowerCase().includes(globalQuery));
        if (aliasContains) score += 200;

        // Query contains alias
        const queryContainsAlias = (p.search_aliases || []).some(a => {
            const al = a.toLowerCase();
            return al.length >= 2 && globalQuery.includes(al);
        });
        if (queryContainsAlias) score += 150;

        // Tenant/owner/manager matches
        const tenantMatch = (p.tenants || []).some(t => t.toLowerCase().includes(globalQuery));
        const subOrgMatch = (p.tenant_sub_orgs || []).some(s => s.toLowerCase().includes(globalQuery));
        const ownerMatch = (p.owners || []).some(o => o.toLowerCase().includes(globalQuery));
        const managerMatch = (p.managers || []).some(m => m.toLowerCase().includes(globalQuery));
        if (tenantMatch) score += 50;
        if (subOrgMatch) score += 40;
        if (ownerMatch) score += 30;
        if (managerMatch) score += 20;

        // Add building count as tiebreaker
        if (score > 0) {
            score += Math.min(p.building_count / 50, 10);
            scored.push({
                idx: p.idx,
                score: score,
                name: p.org_name,
                display: p.display_name,
                buildings: p.building_count
            });
        }
    });

    scored.sort((a, b) => b.score - a.score);
    return scored;
}

// TEST RANKING FOR CONFLICTING TERMS
console.log('='.repeat(70));
console.log('SEARCH RANKING TEST - Conflicting Terms');
console.log('='.repeat(70));

const conflictingQueries = [
    { query: 'usc', expectedFirst: 'USC' },
    { query: 'u of c', expectedTop: ['UC System', 'UChicago'] },
    { query: 'cal', expectedTop: ['UC System', 'Cal State'] },
    { query: 'mit', expectedFirst: 'MIT' },
    { query: 'nyc', expectedFirst: 'New York City' },
    { query: 'la', expectedFirst: 'Los Angeles' },
    { query: 'dc', expectedTop: ['DC Public Schools', 'Washington DC'] },  // Both are valid DC results
    { query: 'jll', expectedFirst: 'JLL' },
    { query: 'gsa', expectedFirst: 'GSA' },
    { query: 'harvard', expectedFirst: 'Harvard' },
    { query: 'stanford', expectedFirst: 'Stanford' },
];

let passed = 0;
let failed = 0;

conflictingQueries.forEach(({ query, expectedFirst, expectedTop }) => {
    const results = globalSearch(query);
    const top5 = results.slice(0, 5);

    console.log(`\n🔍 "${query}" → ${results.length} results`);
    console.log('   Top 5 (ranked):');
    top5.forEach((r, i) => {
        console.log(`     ${i+1}. ${r.display} (score: ${r.score.toFixed(1)}, ${r.buildings} bldgs)`);
    });

    // Check if expected is in top position
    if (expectedFirst) {
        const firstMatch = top5[0]?.display?.toLowerCase().includes(expectedFirst.toLowerCase());
        if (firstMatch) {
            console.log(`   ✅ "${expectedFirst}" is #1`);
            passed++;
        } else {
            console.log(`   ❌ Expected "${expectedFirst}" as #1`);
            failed++;
        }
    }

    if (expectedTop) {
        const topNames = top5.map(r => r.display.toLowerCase());
        const allFound = expectedTop.every(exp =>
            topNames.some(n => n.includes(exp.toLowerCase()))
        );
        if (allFound) {
            console.log(`   ✅ All expected in top 5: ${expectedTop.join(', ')}`);
            passed++;
        } else {
            console.log(`   ❌ Missing from top 5: ${expectedTop.join(', ')}`);
            failed++;
        }
    }
});

console.log('\n' + '='.repeat(70));
console.log(`RESULTS: ${passed} passed, ${failed} failed`);
console.log('='.repeat(70));

if (failed > 0) process.exit(1);
