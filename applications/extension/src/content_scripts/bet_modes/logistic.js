/**
 * Logistic Regression Strategy (ELO Divergence)
 *
 * Since we cannot see the Pot Odds until it's too late, we use
 * "ELO Probability" as a proxy for the Crowd's opinion.
 *
 * 1. Model Win Probability (Our Brain): Calculated from H2H, Comp, Stats.
 * 2. ELO Win Probability (The Crowd): Calculated purely from Tier ELO diff.
 * 3. Divergence (The Edge): The difference between Our Brain and The Crowd.
 *
 * If we see a win (high Model Prob) that the Crowd misses (low ELO Prob),
 * we bet bigger because the payout will likely be good.
 */

import {
    calculateRedVsBlueMatchData,
    calculateComparativeStats,
    calculatePredictability,
} from '../../utils/match.js'

// REPLACE WITH YOUR TRAINED VALUES from train_model.py
const COEFF_INTERCEPT = 0.0
const COEFF_TIER_ELO = 0.0057
const COEFF_H2H = 4.0
const COEFF_COMP = 2.0

const MIN_MATCHES = 3

function logisticBet(matchData) {
    let betData = {
        colour: 'red',
        confidence: null,
        modelScore: 0,
    }

    let fighterRedInfo = matchData.fighter_red_info
    let fighterBlueInfo = matchData.fighter_blue_info

    if (fighterRedInfo == null || fighterBlueInfo == null) {
        return betData
    }

    // --- 1. Logistic Model Calculation (Our "True" Probability) ---
    const tierEloDiff = fighterRedInfo.tier_elo - fighterBlueInfo.tier_elo

    let h2hFeature = 0.0
    const h2hData = calculateRedVsBlueMatchData(
        fighterRedInfo.matches,
        fighterRedInfo.id,
        fighterBlueInfo.id
    )
    if (h2hData.redMatchesVsBlue >= MIN_MATCHES) {
        const h2hWinRate = h2hData.redWinsVsBlue / h2hData.redMatchesVsBlue
        h2hFeature = h2hWinRate - 0.5
    }

    let compFeature = 0.0
    const compStats = calculateComparativeStats(fighterRedInfo, fighterBlueInfo)
    if (compStats) {
        const totalCompMatches =
            compStats.redCompareWon + compStats.redCompareLost
        if (totalCompMatches >= MIN_MATCHES) {
            const compWinRate = compStats.redCompareWon / totalCompMatches
            compFeature = compWinRate - 0.5
        }
    }

    const z =
        COEFF_INTERCEPT +
        COEFF_TIER_ELO * tierEloDiff +
        COEFF_H2H * h2hFeature +
        COEFF_COMP * compFeature

    // The Model's calculated probability for Red
    const modelProbRed = 1 / (1 + Math.exp(-z))

    // Determine our pick
    let myPick = modelProbRed > 0.5 ? 'red' : 'blue'
    let myModelProb = modelProbRed > 0.5 ? modelProbRed : 1 - modelProbRed
    
    betData.modelScore = z
    betData.colour = myPick

    // --- 2. ELO Probability (The "Crowd" Proxy) ---
    // This estimates what the crowd thinks based on ELO difference.
    // Standard ELO formula: 1 / (1 + 10^(diff/400))
    const eloProbRed = 1 / (1 + Math.pow(10, (fighterBlueInfo.tier_elo - fighterRedInfo.tier_elo) / 400))
    const myEloProb = myPick === 'red' ? eloProbRed : 1 - eloProbRed

    // --- 3. Calculate "Edge" (Divergence) ---
    // If Model says 80% and ELO says 50%, Edge is +0.30 (Huge Value).
    // If Model says 60% and ELO says 80%, Edge is -0.20 (Bad Value).
    const edge = myModelProb - myEloProb

    // --- 4. Staking Strategy ---
    // Start with our model's confidence
    let finalConfidence = myModelProb

    // Adjust based on Edge
    // If we have a positive edge, boost the bet (up to 1.5x).
    // If we have a negative edge, cut the bet (down to 0.5x).
    const EDGE_MULTIPLIER = 1.5 // Tunable aggression factor
    const edgeFactor = 1 + (edge * EDGE_MULTIPLIER)
    
    finalConfidence = finalConfidence * edgeFactor

    // --- 5. Stability Adjustment (Predictability) ---
    // Always apply the "Chaos Penalty"
    let predictability = calculatePredictability(myPick === 'red' ? fighterRedInfo : fighterBlueInfo) ?? 1.0
    finalConfidence = finalConfidence * predictability

    // Sanity Cap (0% to 100%)
    betData.confidence = Math.min(Math.max(finalConfidence, 0), 1)

    return betData
}

export { logisticBet as default }