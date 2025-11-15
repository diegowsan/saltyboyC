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

export { calculateRedVsBlueMatchData, calculateComparativeStats }
