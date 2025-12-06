/**
 * Calculate RvB fights.
 *
 * @param {Array.<object>} matches
 * @param {number} fighterRedId
 * @param {number} fighterBlueId
 * @returns
 */
function calculateRedVsBlueMatchData(matches, fighterRedId, fighterBlueId) {
    let redWinsVsBlue = 0
    let redMatchesVsBlue = 0
    let redBetVsBlue = 0
    let blueBetVsRed = 0

    if (!matches) {
        return {
            redWinsVsBlue: 0,
            redMatchesVsBlue: 0,
            redBetVsBlue: 0,
            blueBetVsRed: 0,
        }
    }

    for (const match of matches) {
        if (
            (match.fighter_red == fighterRedId &&
                match.fighter_blue == fighterBlueId) ||
            (match.fighter_red == fighterBlueId &&
                match.fighter_blue == fighterRedId)
        ) {
            if (match.winner == fighterRedId) {
                redWinsVsBlue += 1
            }
            redMatchesVsBlue += 1
            if (match.fighter_red == fighterRedId) {
                redBetVsBlue += match.bet_red
                blueBetVsRed += match.bet_blue
            } else {
                redBetVsBlue += match.bet_blue
                blueBetVsRed += match.bet_red
            }
        }
    }

    return {
        redWinsVsBlue: redWinsVsBlue,
        redMatchesVsBlue: redMatchesVsBlue,
        redBetVsBlue: redBetVsBlue,
        blueBetVsRed: blueBetVsRed,
    }
}

/**
 * Calculates comparative stats based on common opponents.
 * - "Compare Won" (redCompareWon): Opponents Red WON against that Blue LOST against.
 * - "Compare Lost" (redCompareLost): Opponents Red LOST against that Blue WON against.
 * - And vice-versa for Blue.
 *
 * @param {object} fighterRedInfo - Full fighter info object for Red, including matches.
 * @param {object} fighterBlueInfo - Full fighter info object for Blue, including matches.
 * @returns {object | null} - An object with { redCompareWon, redCompareLost, blueCompareWon, blueCompareLost } or null.
 */
function calculateComparativeStats(fighterRedInfo, fighterBlueInfo) {
    if (
        !fighterRedInfo ||
        !fighterBlueInfo ||
        !fighterRedInfo.matches ||
        !fighterBlueInfo.matches
    ) {
        return null
    }

    const redId = fighterRedInfo.id
    const blueId = fighterBlueInfo.id

    const redWonAgainst = new Set()
    const redLostAgainst = new Set()
    const blueWonAgainst = new Set()
    const blueLostAgainst = new Set()

    // Process Red's matches
    for (const match of fighterRedInfo.matches) {
        const opponentId =
            match.fighter_red === redId ? match.fighter_blue : match.fighter_red
        if (opponentId === blueId) continue // Skip direct H2H matches

        if (match.winner === redId) {
            redWonAgainst.add(opponentId)
        } else {
            redLostAgainst.add(opponentId)
        }
    }

    // Process Blue's matches
    for (const match of fighterBlueInfo.matches) {
        const opponentId =
            match.fighter_red === blueId ? match.fighter_blue : match.fighter_red
        if (opponentId === redId) continue // Skip direct H2H matches

        if (match.winner === blueId) {
            blueWonAgainst.add(opponentId)
        } else {
            blueLostAgainst.add(opponentId)
        }
    }

    let redCompareWon = 0
    let redCompareLost = 0
    let blueCompareWon = 0
    let blueCompareLost = 0

    // Find all unique common opponents
    const allOpponents = new Set([
        ...redWonAgainst,
        ...redLostAgainst,
        ...blueWonAgainst,
        ...blueLostAgainst,
    ])

    // Calculate the comparative stats
    for (const oppId of allOpponents) {
        const redWon = redWonAgainst.has(oppId)
        const redLost = redLostAgainst.has(oppId)
        const blueWon = blueWonAgainst.has(oppId)
        const blueLost = blueLostAgainst.has(oppId)

        // Red "Compare Won": Red won AND Blue lost
        if (redWon && blueLost) {
            redCompareWon++
        }
        // Red "Compare Lost": Red lost AND Blue won
        if (redLost && blueWon) {
            redCompareLost++
        }
        // Blue "Compare Won": Blue won AND Red lost
        if (blueWon && redLost) {
            blueCompareWon++
        }
        // Blue "Compare Lost": Blue lost AND Red won
        if (blueLost && redWon) {
            blueCompareLost++
        }
    }

    return { redCompareWon, redCompareLost, blueCompareWon, blueCompareLost }
}

/**
 * Calculates the "Predictability Index" of a fighter.
 * This measures how often the fighter's actual results align with the
 * crowd's betting odds.
 *
 * Mathematical Basis: 1 - (Brier Score)
 * Range: 0.0 (Total Chaos) to 1.0 (Perfectly Predictable)
 *
 * @param {object} fighterInfo - The fighter info object containing 'matches'.
 * @returns {number | null} - The index between 0 and 1, or null if no data.
 */
function calculatePredictability(fighterInfo) {
    if (
        !fighterInfo ||
        !fighterInfo.matches ||
        fighterInfo.matches.length === 0
    ) {
        return null
    }

    let totalSquaredError = 0
    let count = 0

    for (const match of fighterInfo.matches) {
        // Skip matches with no betting data
        if (match.bet_red === 0 && match.bet_blue === 0) continue

        // 1. Calculate what the Crowd thought the probability was.
        let crowdProb = 0
        const totalPot = match.bet_red + match.bet_blue

        if (match.fighter_red === fighterInfo.id) {
            crowdProb = match.bet_red / totalPot
        } else {
            crowdProb = match.bet_blue / totalPot
        }

        // 2. Determine the actual outcome (1 for Win, 0 for Loss).
        const actualResult = match.winner === fighterInfo.id ? 1 : 0

        // 3. Calculate Squared Error (Brier Score component).
        // If Crowd said 90% (0.9) and they lost (0), error is (0.9 - 0)^2 = 0.81 (Huge penalty)
        // If Crowd said 90% (0.9) and they won (1), error is (0.9 - 1)^2 = 0.01 (Tiny penalty)
        totalSquaredError += Math.pow(crowdProb - actualResult, 2)
        count++
    }

    if (count === 0) return null

    const averageError = totalSquaredError / count

    // Invert it so 1.0 is "Good/Predictable" and 0.0 is "Bad/Unpredictable"
    return 1 - averageError
}

export {
    calculateRedVsBlueMatchData,
    calculateComparativeStats,
    calculatePredictability,
}