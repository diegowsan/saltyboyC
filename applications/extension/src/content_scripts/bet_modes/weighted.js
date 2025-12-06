/**
 * Weighted Confidence Strategy
 *
 * This strategy calculates a final probability by blending three factors:
 * 1. Tier ELO (Baseline)
 * 2. Head-to-Head (H2H) Win Rate
 * 3. Comparative W/L Win Rate
 *
 * It assigns weights to each stat based on its reliability (e.g., H2H and
 * Comparative stats are only trusted if they have >= 3 matches).
 * The final confidence is the weighted average of all reliable factors.
 */

import {
    calculateRedVsBlueMatchData,
    calculateComparativeStats,
} from '../../utils/match.js'

function weightedBet(matchData) {
    let betData = {
        colour: 'red',
        confidence: null, // Default to null (which becomes a $1 bet)
    }

    let fighterRedInfo = matchData.fighter_red_info
    let fighterBlueInfo = matchData.fighter_blue_info

    // Step 0: Data & Sanity Check
    if (fighterRedInfo == null || fighterBlueInfo == null) {
        return betData // Bet $1 on Red if any fighter is new
    }

    // --- Define Weights ---
    const W_ELO = 2
    const W_H2H = 5
    const W_COMP = 3
    const MIN_MATCHES = 3 // Min matches needed to trust H2H or Comp stats

    // --- Factor 1: Tier ELO Probability ---
    let eloProb =
        1 /
        (1 +
            Math.pow(
                10,
                (fighterBlueInfo.tier_elo - fighterRedInfo.tier_elo) / 400
            ))
    let totalWeight = W_ELO
    let totalScore = eloProb * W_ELO

    // --- Factor 2: H2H Probability ---
    let h2hData = calculateRedVsBlueMatchData(
        fighterRedInfo.matches,
        fighterRedInfo.id,
        fighterBlueInfo.id
    )
    if (h2hData.redMatchesVsBlue >= MIN_MATCHES) {
        let h2hProb = h2hData.redWinsVsBlue / h2hData.redMatchesVsBlue
        totalWeight += W_H2H
        totalScore += h2hProb * W_H2H
    }

    // --- Factor 3: Comparative Stats Probability ---
    let compStats = calculateComparativeStats(fighterRedInfo, fighterBlueInfo)
    if (compStats) {
        let totalCompMatches = compStats.redCompareWon + compStats.redCompareLost
        if (totalCompMatches >= MIN_MATCHES) {
            let compProb = compStats.redCompareWon / totalCompMatches
            totalWeight += W_COMP
            totalScore += compProb * W_COMP
        }
    }

    // --- Final Calculation ---
    // Calculate the weighted average probability
    let finalProbRed = totalScore / totalWeight

    if (finalProbRed > 0.5) {
        betData.colour = 'red'
        betData.confidence = finalProbRed
    } else {
        betData.colour = 'blue'
        betData.confidence = 1 - finalProbRed
    }

    return betData
}

export { weightedBet as default }