/**
 * Logistic Regression Betting Strategy (Risk-Adjusted)
 *
 * This advanced strategy uses a logistic regression model to calculate
 * a win probability, and then scales that probability based on the
 * fighter's "Predictability Index" (Stability).
 *
 * 1. Model Score (z): Calculated from Tier ELO, H2H, and Comp Stats.
 * 2. Raw Probability: Sigmoid(z).
 * 3. Risk Adjustment: The wager confidence is multiplied by the fighter's
 * predictability score.
 *
 * Example:
 * - Model says 80% win chance (0.80).
 * - Fighter is chaotic (Predictability 0.50).
 * - Final Confidence = 0.80 * 0.50 = 0.40 (40%).
 * - Result: The bot skips the bet (below 65% threshold) or bets small.
 */

import {
    calculateRedVsBlueMatchData,
    calculateComparativeStats,
    calculatePredictability, // <-- Import the new stat
} from '../../utils/match.js'

function logisticBet(matchData) {
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

    // --- Define Model Coefficients (Weights) ---
    // Trained weights can be inserted here later.
    const COEFF_INTERCEPT = 0.0
    const COEFF_TIER_ELO = 0.0057
    const COEFF_H2H = 4.0
    const COEFF_COMP = 2.0

    const MIN_MATCHES = 3

    // --- Feature 1: Tier ELO ---
    const tierEloDiff = fighterRedInfo.tier_elo - fighterBlueInfo.tier_elo

    // --- Feature 2: Head-to-Head (H2H) ---
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

    // --- Feature 3: Comparative (Comp) Stats ---
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

    // --- Calculate Final Score (z) ---
    const z =
        COEFF_INTERCEPT +
        COEFF_TIER_ELO * tierEloDiff +
        COEFF_H2H * h2hFeature +
        COEFF_COMP * compFeature

    // --- Raw Probability (Sigmoid) ---
    const probRedWin = 1 / (1 + Math.exp(-z))

    // --- Risk Adjustment (Predictability Multiplier) ---
    // We determine who we are betting on, and then check their stability.
    let target = 'red'
    let rawConfidence = probRedWin
    let fighterToBetOn = fighterRedInfo

    if (probRedWin < 0.5) {
        target = 'blue'
        rawConfidence = 1 - probRedWin
        fighterToBetOn = fighterBlueInfo
    }

    // Calculate Predictability (0.0 to 1.0)
    let predictability = calculatePredictability(fighterToBetOn)

    // Default to 1.0 (no penalty) if we have no data to judge stability
    if (predictability === null) {
        predictability = 1.0
    }

    // Apply the multiplier
    // A stable fighter (0.95) keeps 95% of the confidence.
    // An unstable fighter (0.60) keeps only 60% of the confidence.
    const riskAdjustedConfidence = rawConfidence * predictability

    betData.colour = target
    betData.confidence = riskAdjustedConfidence

    return betData
}

export { logisticBet as default }