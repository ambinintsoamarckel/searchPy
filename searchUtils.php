<?php
declare(strict_types=1);

namespace App\Utils;

use Meilisearch\Endpoints\Indexes;
use App\Command\SearchDefaults;

/**
 * SearchUtils (version améliorée avec no_space et scoring hybride)
 * - Stratégie no_space pour gérer les mots collés
 * - MAX entre name_search et no_space
 * - Scoring phonétique hybride
 * - CAP strict à 9.99 sauf exact_full
 * - Score 10.0 = réservé aux matchs parfaits uniquement
 */
final class SearchUtils
{
    // ---------- Config / constantes ----------
    private array $searchCache = [];
    private int $maxCacheSize = 1000;
    private int $cacheTtl = 3600;

    private StringDistance $lev;
    private array $synonyms;

    private const MAX_LEVENSHTEIN_DISTANCE_DEFAULT = 4;
    private int $currentMaxLev = self::MAX_LEVENSHTEIN_DISTANCE_DEFAULT;

    // Priorités de type d'appariement
    private const TYPE_PRIORITY = [
        'exact_full'         => 0,
        'exact_with_extras'  => 1,
        'no_space_match'     => 1,
        'near_perfect'       => 2,
        'phonetic_strict'    => 3,
        'exact_with_missing' => 4,
        'fuzzy_full'         => 5,
        'hybrid'             => 6,
        'phonetic_tolerant'  => 7,
        'fuzzy_partial'      => 8,
        'partial'            => 9,
    ];

    // Poids des pénalités
    private const W_MISSING = 0.6;
    private const W_FUZZY   = 0.5;
    private const W_RATIO   = 1.0;
    private const W_EXTRA_LENGTH = 0.15;

    // Bonus name
    private const BONUS_MAX = 2.0;
    private const BONUS_A_MISSING = 0.3;
    private const BONUS_C_AVGDIST = 0.35;

    // Gates pour bonus
    private const BONUS_WORD_RATIO_MIN = 0.4;
    private const BONUS_EXTRA_RATIO_MAX = 1.0;

    // Seuil exact
    private const EXACT_THRESHOLD = 10.0;
    private const EXACT_FULL_CAP = 9.99;

    // Seuil minimal no_space
    private const NO_SPACE_MIN_SCORE = 7.0;

    public function __construct(?StringDistance $lev = null, array $synonyms = [])
    {
        $this->lev = $lev ?? new StringDistance();

        $norm = [];
        foreach (($synonyms ?: SearchDefaults::synonyms()) as $base => $syns) {
            $baseL = mb_strtolower($base);
            $norm[$baseL] = array_values(array_unique(array_map('mb_strtolower', $syns)));
        }
        $this->synonyms = $norm;
    }

    private function preprocessQuery(string $query): array
    {
        $query = trim($query);
        if ($query === '') return ['original_length' => 0];

        $original = SearchTextNormalizer::normalizeQuery($query);
        $cleaned  = SearchTextNormalizer::cleanUserQuery($query);
        $noSpace  = str_replace(' ', '', $cleaned);

        return [
            'original'         => $original,
            'cleaned'          => $cleaned,
            'no_space'         => $noSpace,
            'soundex'          => SearchTextNormalizer::soundexFrench($cleaned),
            'original_length'  => mb_strlen($original),
            'cleaned_length'   => mb_strlen($cleaned),
            'no_space_length'  => mb_strlen($noSpace),
            'wordsCleaned'     => array_values(array_filter(preg_split('/\s+/', $cleaned))),
            'wordsOriginal'    => array_values(array_filter(preg_split('/\s+/', $original))),
            'wordsNoSpace'     => [$noSpace],
        ];
    }

    // ---------- Synonymes ----------
    private function applySynonyms(string $word1, string $word2): ?string
    {
        $w1 = mb_strtolower($word1);
        $w2 = mb_strtolower($word2);

        foreach ($this->synonyms as $base => $syns) {
            $in1 = ($w1 === $base) || in_array($w1, $syns, true);
            $in2 = ($w2 === $base) || in_array($w2, $syns, true);
            if ($in1 && $in2) return $word2;
        }
        return null;
    }

    // ---------- Matching de mots ----------
    private function calculateWordMatch(string $queryWord, string $candidateWord): array
    {
        $q = mb_strtolower($queryWord);
        $c = mb_strtolower($candidateWord);

        if ($q === $c) {
            return ['distance' => 0, 'type' => 'exact', 'matched_word' => $candidateWord];
        }

        if ($this->applySynonyms($q, $c) !== null) {
            return ['distance' => 0, 'type' => 'synonym', 'matched_word' => $candidateWord];
        }

        $maxDistance = min($this->currentMaxLev, $this->lev->dynamicMax($q));
        $distance = $this->lev->distance($q, $c, $maxDistance);

        return [
            'distance'     => $distance,
            'type'         => 'levenshtein',
            'matched_word' => $candidateWord,
        ];
    }

    private function findBestWordMatchInCandidate(string $queryWord, array $candidateWords, array &$usedPositions): ?array
    {
        $bestMatch = null;
        $bestDistance = $this->currentMaxLev + 1;

        foreach ($candidateWords as $position => $candidateWord) {
            if (!empty($usedPositions[$position])) continue;

            $match = $this->calculateWordMatch($queryWord, $candidateWord);
            if ($match['distance'] < $bestDistance) {
                $bestMatch   = $match + ['position' => $position];
                $bestDistance = $match['distance'];
                if ($bestDistance === 0) break;
            }
        }

        if ($bestMatch) {
            $usedPositions[$bestMatch['position']] = true;
        }
        return $bestMatch;
    }

    // ---------- Évaluation 1-pass d'un champ ----------
    private function evaluateField(array $queryWords, array $candidateWords, string $queryText): array
    {
        $found = [];
        $notFound = [];
        $totalDistance = 0;
        $usedPositions = [];

        foreach ($queryWords as $q) {
            $best = $this->findBestWordMatchInCandidate($q, $candidateWords, $usedPositions);
            if ($best && $best['distance'] <= $this->currentMaxLev) {
                $found[] = [
                    'query_word'   => $q,
                    'matched_word' => $best['matched_word'],
                    'distance'     => $best['distance'],
                    'type'         => $best['type'],
                    'position'     => $best['position'],
                ];
                $totalDistance += $best['distance'];
            } else {
                $notFound[] = $q;
            }
        }

        $foundCount = count($found);
        $qCount     = count($queryWords);
        $rCount     = count($candidateWords);

        $avgDistance   = $foundCount > 0 ? $totalDistance / $foundCount : 0.0;
        $missingTerms  = count($notFound);
        $lengthRatio   = ($rCount && $qCount) ? min($qCount, $rCount) / max($qCount, $rCount) : 1.0;
        $coverageRatio = $qCount > 0 ? $foundCount / $qCount : 1.0;

        // Calcul de la longueur des extras
        $extraLength = 0;
        $foundPositions = array_column($found, 'position');
        foreach ($candidateWords as $pos => $word) {
            if (!in_array($pos, $foundPositions)) {
                $extraLength += mb_strlen($word);
            }
        }

        $queryLength = mb_strlen($queryText);
        $extraLengthRatio = $queryLength > 0 ? $extraLength / $queryLength : 0.0;

        return [
            'found'            => $found,
            'not_found'        => $notFound,
            'total_distance'   => $totalDistance,
            'average_distance' => $avgDistance,
            'found_count'      => $foundCount,
            'query_count'      => $qCount,
            'result_count'     => $rCount,
            'extra_length'     => $extraLength,
            'extra_length_ratio' => $extraLengthRatio,
            'penalties'        => [
                'mots_manquants'      => $missingTerms,
                'distance_moyenne'    => $avgDistance,
                'longueur_ratio'      => $lengthRatio,
                'coverage_ratio'      => $coverageRatio,
                'extra_length'        => $extraLength,
                'extra_length_ratio'  => $extraLengthRatio,
            ],
        ];
    }

    // ---------- Phonétique ----------
    private function phoneticTokens(string $s): array
    {
        $toks = preg_split('/\s+/', mb_strtolower(trim($s)));
        return array_values(array_filter($toks, fn($t) => $t !== '' && mb_strlen($t) > 1));
    }

    private function matchPhoneticTokens(array $qTokens, array $hTokens, bool $tolerant = false): array
    {
        $used = [];
        $matches = 0;
        $tolerantUsed = false;

        foreach ($qTokens as $qt) {
            $bestIdx = null;
            $isTolerant = false;

            foreach ($hTokens as $i => $ct) {
                if (!empty($used[$i])) continue;

                if ($qt === $ct) { $bestIdx = $i; $isTolerant = false; break; }

                $minlen = min(mb_strlen($qt), mb_strlen($ct));
                if ($minlen >= 4 && (mb_strpos($qt, $ct) === 0 || mb_strpos($ct, $qt) === 0)) {
                    if ($bestIdx === null) { $bestIdx = $i; $isTolerant = false; }
                    continue;
                }

                if ($tolerant && $minlen >= 6) {
                    if ($this->lev->distance($qt, $ct, 1) <= 1) {
                        if ($bestIdx === null) { $bestIdx = $i; $isTolerant = true; }
                    }
                }
            }

            if ($bestIdx !== null) {
                $used[$bestIdx] = true;
                $matches++;
                if ($isTolerant) $tolerantUsed = true;
            }
        }

        return ['found' => $matches, 'tolerant_used' => $tolerantUsed];
    }

    private function calculatePhoneticScore(array $hit, array $queryData): ?array
    {
        $q = trim((string)($queryData['soundex'] ?? ''));
        $h = trim((string)($hit['name_soundex'] ?? ''));
        if ($q === '' || $h === '') return null;

        $qT = $this->phoneticTokens($q);
        $hT = $this->phoneticTokens($h);
        if (!$qT || !$hT) return null;

        $strict = $this->matchPhoneticTokens($qT, $hT, false);
        $ratio  = $strict['found'] / count($qT);
        $type   = 'phonetic_strict';

        $score = 8 * $ratio;
        if ($ratio === 1.0)      $score = min(7.5, $score);
        elseif ($ratio >= 0.66)  $score = min(7.0, $score);
        else                     $score = min(6.0, $score);

        if ($score < 6.0) {
            $tol = $this->matchPhoneticTokens($qT, $hT, true);
            $ratioTol = $tol['found'] / count($qT);
            if ($ratioTol > $ratio) {
                $ratio = $ratioTol;
                $type  = 'phonetic_tolerant';
                $score = 8 * $ratio;
                if ($ratio === 1.0)      $score = min(7.5, $score);
                elseif ($ratio >= 0.66)  $score = min(7.0, $score);
                else                     $score = min(6.0, $score);
            }
        }

        return [
            'score'         => $score,
            'ratio'         => $ratio,
            'match_type'    => $type,
            'query_soundex' => $q,
            'hit_soundex'   => $h,
            'tokens'        => ['q' => $qT, 'h' => $hT],
        ];
    }

    // ---------- Score principal avec MAX name_search / no_space ----------
    private function calculateMainScore(array $hit, array $queryData): array
    {
        $queryCleanWords    = $queryData['wordsCleaned'];
        $queryOriginalWords = $queryData['wordsOriginal'];
        $queryNoSpaceWords  = $queryData['wordsNoSpace'];

        if (empty($queryCleanWords)) {
            return [
                'name_search_score' => 0.0,
                'no_space_score'    => 0.0,
                'base_score'        => 0.0,
                'name_score'        => 0.0,
                'total_score'       => 0.0,
                'winning_strategy'  => 'none',
                '_penalty_indices'  => [],
                'details'           => ['error' => 'empty_query'],
                'all_words_found'   => false,
                'match_type'        => 'partial',
                'match_priority'    => self::TYPE_PRIORITY['partial'],
            ];
        }

        $nameSearch  = (string)($hit['name_search']   ?? '');
        $nameNoSpace = (string)($hit['name_no_space'] ?? '');
        $name        = (string)($hit['name'] ?? $hit['nom'] ?? '');

        $nameSearchWords  = array_values(array_filter(preg_split('/\s+/', mb_strtolower(trim($nameSearch)) ?: '')));
        $nameNoSpaceWords = array_values(array_filter(preg_split('/\s+/', mb_strtolower(trim($nameNoSpace)) ?: '')));
        $nameWords        = array_values(array_filter(preg_split('/\s+/', mb_strtolower(trim($name)) ?: '')));

        // ---------- 1) name_search ----------
        $evalSearch = $this->evaluateField($queryCleanWords, $nameSearchWords, $queryData['cleaned']);
        $pSearch = $evalSearch['penalties'] ?? [];
        if (($evalSearch['found_count'] ?? 0) === 0) {
            $nameSearchScoreAdj = 0.0; // garde anti "10 - 0" fantôme
        } else {
            $nameSearchScore = 10 - ($evalSearch['total_distance'] ?? 0);
            $nameSearchScore = max(0.0, min(10.0, $nameSearchScore));
            $penaltySearch =
                self::W_MISSING * ($pSearch['mots_manquants'] ?? 0)
            + self::W_FUZZY   * max(0.0, ($pSearch['distance_moyenne'] ?? 0.0))
            + self::W_RATIO   * (1.0 - max(0.0, min(1.0, ($pSearch['longueur_ratio'] ?? 1.0))))
            + self::W_EXTRA_LENGTH * ($pSearch['extra_length_ratio'] ?? 0.0) * 10;
            $nameSearchScoreAdj = max(0.0, $nameSearchScore - $penaltySearch);
        }

        // ---------- 2) no_space ----------
        $evalNoSpace = $this->evaluateField($queryNoSpaceWords, $nameNoSpaceWords, $queryData['no_space']);
        $pNoSpace = $evalNoSpace['penalties'] ?? [];
        if (($evalNoSpace['found_count'] ?? 0) === 0) {
            $noSpaceScoreAdj = 0.0; // garde anti "10 - 0" fantôme
        } else {
            $noSpaceScore = 10 - ($evalNoSpace['total_distance'] ?? 0);
            $noSpaceScore = max(0.0, min(10.0, $noSpaceScore));
            $penaltyNoSpace =
                self::W_MISSING * ($pNoSpace['mots_manquants'] ?? 0)
            + self::W_FUZZY   * max(0.0, ($pNoSpace['distance_moyenne'] ?? 0.0))
            + self::W_RATIO   * (1.0 - max(0.0, min(1.0, ($pNoSpace['longueur_ratio'] ?? 1.0))))
            + self::W_EXTRA_LENGTH * ($pNoSpace['extra_length_ratio'] ?? 0.0) * 10;
            $noSpaceScoreAdj = max(0.0, $noSpaceScore - $penaltyNoSpace);

            // seuil minimal spécifique no_space
            if ($noSpaceScoreAdj < self::NO_SPACE_MIN_SCORE) {
                $noSpaceScoreAdj = 0.0;
            }
        }

        // ---------- 3) Choix de la stratégie gagnante ----------
        // Exige un score > 0 ET au moins 1 match trouvé pour considérer une stratégie "valide"
        $searchValid  = $nameSearchScoreAdj  > 0 && (($evalSearch['found_count']  ?? 0) > 0);
        $noSpaceValid = $noSpaceScoreAdj     > 0 && (($evalNoSpace['found_count'] ?? 0) > 0);

        if ($noSpaceValid && (!$searchValid || $noSpaceScoreAdj >= $nameSearchScoreAdj)) {
            $winningStrategy = 'no_space';
            $baseScore       = $noSpaceScoreAdj;
            $winningEval     = $evalNoSpace;
            $winningPenalties= $pNoSpace;
        } elseif ($searchValid) {
            $winningStrategy = 'name_search';
            $baseScore       = $nameSearchScoreAdj;
            $winningEval     = $evalSearch;
            $winningPenalties= $pSearch;
        } else {
            // aucun des deux n'a trouvé → baseScore=0, partial
            $winningStrategy = 'none';
            $baseScore       = 0.0;
            $winningEval     = $evalSearch;   // arbitraire, pour remplir la structure
            $winningPenalties= $pSearch;
        }

        // ---------- 4) Bonus sur "name" ----------
        $evalName = $this->evaluateField($queryOriginalWords, $nameWords, $queryData['original']);
        $bonus = $this->calculateNameBonus($evalName, $queryOriginalWords, $queryData['original']);

        $totalScore = min(12.0, $baseScore + $bonus);

        // ---------- 5) Match type ----------
        $noWinningMatch = (($winningEval['found_count'] ?? 0) === 0);
        if ($noWinningMatch) {
            $matchType = 'partial';
        } else {
            $avg       = $winningEval['average_distance'];
            $missing   = $winningPenalties['mots_manquants'] ?? 0;
            $extraRatio= $winningPenalties['extra_length_ratio'] ?? 0.0;

            if ($avg == 0.0) {
                if ($missing === 0) {
                    $matchType = ($winningStrategy === 'no_space') ? 'no_space_match' : 'exact_with_extras';
                } else {
                    $matchType = 'exact_with_missing';
                }
            } else {
                $matchType = ($missing === 0) ? 'fuzzy_full' : 'fuzzy_partial';
            }

            if ($matchType === 'fuzzy_full' && $totalScore >= 8.0) {
                $matchType = 'near_perfect';
            }
        }

        return [
            'name_search_score'   => $nameSearchScoreAdj ?? 0.0,
            'no_space_score'      => $noSpaceScoreAdj    ?? 0.0,
            'base_score'          => $baseScore,
            'winning_strategy'    => $winningStrategy,
            'name_score'          => $bonus,
            'total_score'         => $totalScore,
            'name_search_matches' => [
                'found'              => $evalSearch['found'],
                'not_found'          => $evalSearch['not_found'],
                'total_distance'     => $evalSearch['total_distance'],
                'average_distance'   => $evalSearch['average_distance'],
                'extra_length'       => $evalSearch['extra_length'],
                'extra_length_ratio' => $evalSearch['extra_length_ratio'],
            ],
            'no_space_matches'    => [
                'found'              => $evalNoSpace['found'],
                'not_found'          => $evalNoSpace['not_found'],
                'total_distance'     => $evalNoSpace['total_distance'],
                'average_distance'   => $evalNoSpace['average_distance'],
                'extra_length'       => $evalNoSpace['extra_length'],
                'extra_length_ratio' => $evalNoSpace['extra_length_ratio'],
            ],
            'name_matches'        => [
                'found'              => $evalName['found'],
                'not_found'          => $evalName['not_found'],
                'total_distance'     => $evalName['total_distance'],
                'average_distance'   => $evalName['average_distance'],
                'extra_length'       => $evalName['extra_length'],
                'extra_length_ratio' => $evalName['extra_length_ratio'],
            ],
            '_penalty_indices'    => $winningPenalties,
            'all_words_found'     => (($winningPenalties['mots_manquants'] ?? 0) === 0),
            'match_type'          => $matchType,
            'match_priority'      => self::TYPE_PRIORITY[$matchType] ?? self::TYPE_PRIORITY['partial'],
            'details' => [
                'query_words_count'       => count($queryCleanWords),
                'name_search_words_count' => count($nameSearchWords),
                'no_space_words_count'    => count($nameNoSpaceWords),
                'name_words_count'        => count($nameWords),
            ],
        ];
    }



    // ---------- Calcul bonus name progressif ----------
    private function calculateNameBonus(array $evalName, array $queryWords, string $queryText): float
    {
        $queryWordCount = count($queryWords);
        $nameWordCount  = $evalName['result_count'];

        $wordCountRatio = $nameWordCount > 0
            ? min($queryWordCount, $nameWordCount) / max($queryWordCount, $nameWordCount)
            : 0.0;

        $extraLengthRatio = $evalName['extra_length_ratio'] ?? 0.0;

        if ($wordCountRatio < self::BONUS_WORD_RATIO_MIN || $extraLengthRatio > self::BONUS_EXTRA_RATIO_MAX) {
            return 0.0;
        }

        $scoreTerms = 0.0;
        foreach ($evalName['found'] as $m) {
            $dist = $m['distance'];
            if ($dist === 0) {
                $scoreTerms += 1.0;
            } elseif ($dist === 1) {
                $scoreTerms += 0.7;
            } elseif ($dist === 2) {
                $scoreTerms += 0.4;
            } else {
                $scoreTerms += 0.2;
            }
        }

        $maxScore = max(1, $queryWordCount);
        $scoreRatio = $scoreTerms / $maxScore;

        $bonusBase = self::BONUS_MAX * $scoreRatio;

        $pn = $evalName['penalties'];
        $bonusReduction =
            self::BONUS_A_MISSING * ($pn['mots_manquants'] ?? 0)
          + self::BONUS_C_AVGDIST * max(0.0, $evalName['average_distance'] ?? 0.0)
          + self::BONUS_MAX * $extraLengthRatio * 0.6;

        $bonus = max(0.0, min(self::BONUS_MAX, $bonusBase - $bonusReduction));

        $attenuationRange = 1.0 - self::BONUS_WORD_RATIO_MIN;
        $attenuationFactor = ($wordCountRatio - self::BONUS_WORD_RATIO_MIN) / $attenuationRange;
        $attenuationFactor = max(0.0, min(1.0, $attenuationFactor));

        return $bonus * $attenuationFactor;
    }

    // ---------- Scoring phonétique hybride ----------
    private function calculateFinalScore(array $mainScore, ?array $phonScore): array
    {
        $textScore = $mainScore['total_score'];
        $phonValue = $phonScore['score'] ?? 0;

        // Cas 1: Textuel excellent → ignore phonétique
        if ($textScore >= 8.5) {
            return [
                'score' => $textScore,
                'type' => $mainScore['match_type'],
                'method' => 'text_only',
            ];
        }

        // Cas 2: Textuel bon (6-8.5) ET phonétique disponible → hybride
        if ($textScore >= 6.0 && $phonValue > 0) {
            $textWeight = 0.7 + ($textScore / 40);
            $phonWeight = 1.0 - $textWeight;

            $hybrid = ($textScore * $textWeight) + ($phonValue * $phonWeight);

            return [
                'score' => $hybrid,
                'type' => 'hybrid',
                'method' => 'weighted',
                'weights' => ['text' => $textWeight, 'phon' => $phonWeight],
            ];
        }

        // Cas 3: Textuel faible → MAX
        if ($phonValue > $textScore) {
            return [
                'score' => $phonValue,
                'type' => $phonScore['match_type'] ?? 'phonetic',
                'method' => 'phonetic_fallback',
            ];
        }

        // Cas 4: Par défaut textuel
        return [
            'score' => $textScore,
            'type' => $mainScore['match_type'],
            'method' => 'text_only',
        ];
    }

    // ---------- Classification ----------
    private function classifyResult(array $hit, array $queryData): array
    {
        $main = $this->calculateMainScore($hit, $queryData);
        $phon = $this->calculatePhoneticScore($hit, $queryData);

        $final = $this->calculateFinalScore($main, $phon);

        $enriched = $hit;
        $enriched['_score'] = $final['score'];
        $enriched['_match_type'] = $final['type'];
        $enriched['_match_priority'] = self::TYPE_PRIORITY[$final['type']] ?? 999;
        $enriched['_scoring_method'] = $final['method'];
        $enriched['_scoring_details'] = $main;

        if ($phon) {
            $enriched['_phonetic_details'] = $phon;
        }

        if (isset($final['weights'])) {
            $enriched['_scoring_weights'] = $final['weights'];
        }

        // CAP STRICT : seul exact_full peut atteindre 10.0
        if ($enriched['_match_type'] !== 'exact_full' && $enriched['_score'] >= self::EXACT_THRESHOLD) {
            $enriched['_score'] = self::EXACT_FULL_CAP;
            $enriched['_capped'] = true;
        }

        $enriched['_penalty_indices'] = $main['_penalty_indices'] ?? [];

        return $enriched;
    }

    // ---------- Tri ----------
    private function comparePenaltyIndices(array $a, array $b): int
    {
        $extraA = $a['extra_length_ratio'] ?? 0.0;
        $extraB = $b['extra_length_ratio'] ?? 0.0;
        if (abs($extraA - $extraB) > 0.01) return $extraA <=> $extraB;

        $ratioA = $a['longueur_ratio'] ?? 1.0;
        $ratioB = $b['longueur_ratio'] ?? 1.0;
        if (abs($ratioA - $ratioB) > 0.001) return $ratioB <=> $ratioA;

        $distA = $a['distance_moyenne'] ?? 0.0;
        $distB = $b['distance_moyenne'] ?? 0.0;
        return $distA <=> $distB;
    }

    private function compareResults(array $a, array $b): int
    {
        // Tri uniquement par score décroissant
        $sa = $a['_score'] ?? 0.0;
        $sb = $b['_score'] ?? 0.0;

        if ($sa === $sb) {
            // Départage stable par id pour éviter les permutations aléatoires
            if (isset($a['id'], $b['id'])) return $a['id'] <=> $b['id'];
            if (isset($a['id_etab'], $b['id_etab'])) return $a['id_etab'] <=> $b['id_etab'];
            return 0;
        }

        return $sb <=> $sa; // desc
    }



    private function sortResults(array $results): array
    {
        // 1) Mémoriser la position d'origine pour stabiliser le tri (usort n'est pas stable)
        foreach ($results as $i => &$hit) {
            $hit['__pos'] = $i;
        }
        unset($hit);

        // 2) Tri déterministe
        usort($results, function (array $a, array $b): int {
            $sa = $a['_score'] ?? 0.0;
            $sb = $b['_score'] ?? 0.0;

            // (a) Score décroissant
            if ($sa !== $sb) return $sb <=> $sa;

            // (b) Égalités de float : epsilon pour éviter les imprécisions
            $eps = 1e-9;
            if (abs($sa - $sb) > $eps) {
                return ($sb > $sa) ? 1 : -1;
            }

            // (c) Départage par pénalités : moins d'extras, meilleur ratio de longueur, plus faible distance moyenne
            if (isset($a['_penalty_indices'], $b['_penalty_indices'])) {
                $pa = $a['_penalty_indices']; $pb = $b['_penalty_indices'];

                $cmp = ($pa['extra_length_ratio'] ?? 0.0) <=> ($pb['extra_length_ratio'] ?? 0.0);
                if ($cmp !== 0) return $cmp;

                $cmp = ($pb['longueur_ratio'] ?? 1.0) <=> ($pa['longueur_ratio'] ?? 1.0);
                if ($cmp !== 0) return $cmp;

                $cmp = ($pa['distance_moyenne'] ?? 0.0) <=> ($pb['distance_moyenne'] ?? 0.0);
                if ($cmp !== 0) return $cmp;
            }

            // (d) Départage par id (si présent)
            if (isset($a['id'], $b['id']) && $a['id'] !== $b['id']) {
                return $a['id'] <=> $b['id']; // ASC pour être déterministe
            }
            if (isset($a['id_etab'], $b['id_etab']) && $a['id_etab'] !== $b['id_etab']) {
                return $a['id_etab'] <=> $b['id_etab']; // ASC
            }

            // (e) Enfin, position initiale pour rendre le tri STABLE
            return ($a['__pos'] ?? 0) <=> ($b['__pos'] ?? 0);
        });

        // 3) Nettoyage
        foreach ($results as &$hit) {
            unset($hit['__pos']);
        }
        unset($hit);

        return $results;
    }


    // ---------- Meilisearch ----------
    private function executeSearch(Indexes $index, string $query, array $config): array
    {
        try {
            $params = [
                'limit' => $config['limit'],
                'attributesToSearchOn' => $config['attributes'],
            ];

            if (!empty($config['filters'])) {
                $params['filter'] = $config['filters'];
            }

            $res = $index->search($query, $params);

            if (is_object($res) && method_exists($res, 'getHits')) {
                $hits = $res->getHits();
                if (!is_array($hits)) {
                    throw new \RuntimeException('Meilisearch returned non-array from getHits().');
                }
                return $hits;
            }

            if (is_array($res) && isset($res['hits'])) {
                if (!is_array($res['hits'])) {
                    throw new \RuntimeException('Meilisearch returned hits, but hits is not an array.');
                }
                return $res['hits'];
            }

            throw new \RuntimeException('Unsupported Meilisearch response format.');
        } catch (\Throwable $e) {
            throw new \RuntimeException('Meilisearch search error: ' . $e->getMessage(), previous: $e);
        }
    }


    // ---------- Prétraitements ----------
    private function executeAllSearchStrategies(Indexes $index, array $queryData, array $options): array
    {
        $limit   = $options['limit']   ?? 50;
        $filters = $options['filters'] ?? null;

        $allResults = [];

        $strategies = [
            'name_search' => [
                'query'      => $queryData['cleaned'] ?: $queryData['original'],
                'attributes' => ['name_search'],
            ],
            'no_space' => [
                'query'      => $queryData['no_space'],
                'attributes' => ['name_no_space'],
            ],
            'standard' => [
                'query'      => $queryData['original'],
                'attributes' => ['name'],
            ],
        ];

        if (!empty($queryData['soundex'])) {
            $strategies['phonetic'] = [
                'query'      => $queryData['soundex'],
                'attributes' => ['name_soundex'],
            ];
        }

        foreach ($strategies as $strategyName => $cfg) {
            $hits = $this->executeSearch($index, $cfg['query'], [
                'limit'     => $limit,
                'attributes'=> $cfg['attributes'],
                'filters'   => $filters,
            ]);

            foreach ($hits as &$hit) {
                $hit['_discovery_strategy'] = $strategyName;
            }
            unset($hit);

            $allResults[$strategyName] = $hits;
        }

        return $allResults;
    }

    private function deduplicateResults(array $allResults): array
    {
        $unique = [];
        $seen = [];
        $priorityOrder = ['name_search', 'no_space', 'standard', 'phonetic'];

        foreach ($priorityOrder as $strategy) {
            if (!isset($allResults[$strategy])) continue;

            foreach ($allResults[$strategy] as $hit) {
                $id = $hit['id'] ?? $hit['id_etab'] ?? null;
                if ($id !== null && !isset($seen[$id])) {
                    $unique[] = $hit;
                    $seen[$id] = true;
                }
            }
        }
        return $unique;
    }

    // ---------- API principale ----------
    public function search(Indexes $index, string $userQuery, array $options = []): array
    {
        $startTime = microtime(true);

        $cacheKey = $this->getCacheKey($userQuery, $options);
        if ($this->isCacheValid($cacheKey)) {
            $cached = $this->searchCache[$cacheKey];
            $cached['from_cache'] = true;
            return $cached;
        }

        $queryData = $this->preprocessQuery($userQuery);
        if (($queryData['original_length'] ?? 0) === 0) {
            return [
                'hits' => [],
                'total' => 0,
                'query_time_ms' => 0,
                'from_cache' => false,
                'has_exact_results' => false,
                'error' => 'Empty query',
            ];
        }

        $this->currentMaxLev = (int)($options['max_distance'] ?? self::MAX_LEVENSHTEIN_DISTANCE_DEFAULT);
        if ($this->currentMaxLev < 0) $this->currentMaxLev = 0;

        $allResults = $this->executeAllSearchStrategies($index, $queryData, $options);
        $dedup = $this->deduplicateResults($allResults);

        $enriched = [];
        foreach ($dedup as $hit) {
            $enriched[] = $this->classifyResult($hit, $queryData);
        }

        $sorted = $this->sortResults($enriched);

        // Détection résultats exacts (≥ 10)
        $exactResults = array_filter($sorted, fn($hit) => ($hit['_score'] ?? 0) >= self::EXACT_THRESHOLD);
        $hasExactResults = count($exactResults) > 0;

        // Si exact → retourner SEULEMENT les exacts
        $finalHits = $hasExactResults ? $exactResults : $sorted;

        $limit = $options['limit'] ?? 10;
        $finalHits = array_slice($finalHits, 0, $limit);

        $endTime = microtime(true);
        $result = [
            'hits' => $finalHits,
            'total' => count($finalHits),
            'has_exact_results' => $hasExactResults,
            'exact_count' => count($exactResults),
            'total_before_filter' => count($sorted),
            'query_time_ms' => round(($endTime - $startTime) * 1000, 2),
            'preprocessing' => $queryData,
            'from_cache' => false,
        ];

        $this->cacheResult($cacheKey, $result);
        $this->currentMaxLev = self::MAX_LEVENSHTEIN_DISTANCE_DEFAULT;

        return $result;
    }

    // ---------- Cache ----------
    private function getCacheKey(string $query, array $options): string
    {
        return md5($query . json_encode($options, JSON_UNESCAPED_UNICODE|JSON_PRESERVE_ZERO_FRACTION));
    }

    private function isCacheValid(string $key): bool
    {
        return isset($this->searchCache[$key]) &&
               (time() - ($this->searchCache[$key]['cached_at'] ?? 0)) < $this->cacheTtl;
    }

    private function cacheResult(string $key, array $result): void
    {
        if (count($this->searchCache) >= $this->maxCacheSize) {
            $this->cleanOldCache();
        }
        $result['cached_at'] = time();
        $this->searchCache[$key] = $result;
    }

    private function cleanOldCache(): void
    {
        $now = time();
        $this->searchCache = array_filter(
            $this->searchCache,
            fn($item) => ($now - ($item['cached_at'] ?? 0)) < $this->cacheTtl
        );
    }

    // ---------- Public helpers ----------
    public function clearCache(): void
    {
        $this->searchCache = [];
    }

    public function setSynonyms(array $synonyms): void
    {
        $norm = [];
        foreach ($synonyms as $base => $syns) {
            $baseL = mb_strtolower($base);
            $norm[$baseL] = array_values(array_unique(array_map('mb_strtolower', $syns)));
        }
        $this->synonyms = $norm;
    }

    public function getSynonyms(): array
    {
        return $this->synonyms;
    }

    public function getCacheStats(): array
    {
        return [
            'size' => count($this->searchCache),
            'max_size' => $this->maxCacheSize,
            'ttl' => $this->cacheTtl,
        ];
    }
}
