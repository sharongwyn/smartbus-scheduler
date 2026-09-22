import random
import math
from typing import List, Dict, Tuple, Set, Optional, Callable
from data import ROUTES, Trip, TOTAL_TRIPS


class ACO:
    def __init__(
        self,
        n_ants: int = 30,
        n_iterations: int = 100,
        alpha: float = 1.0,
        beta: float = 2.0,
        rho: float = 0.1,
        q: float = 100.0,
        n_trips: int = TOTAL_TRIPS,  
        stagnation_limit: int = 12,
        candidate_list_size: int = 8,
        use_local_pheromone: bool = False,
        rho_local: float = 0.05,
        w_inv_dist: float = 0.35,
        w_connectivity: float = 0.30,
        w_successor_degree: float = 0.20,
        w_city_balance: float = 0.15,
        fw_coverage: float = 12_000.0,
        fw_distance: float = 0.1,
        fw_teleport: float = 1_200.0,
        fw_repetition: float = 40.0,
        fw_loop: float = 100.0,
        fw_continuity: float = 300.0,
        fw_connectivity: float = 150.0,
        fw_city_coverage: float = 500.0,
        fw_dead_end: float = 200.0,
        fw_smoothness: float = 80.0,
        callback: Optional[Callable] = None,
    ):
        self.n_ants_start = int(n_ants * 1.5)
        self.n_ants_end   = max(10, int(n_ants * 0.6))
        self.n_ants       = self.n_ants_start
        self.n_iterations        = n_iterations
        self.q                   = q
        self.n_trips             = n_trips
        self.stagnation_limit    = stagnation_limit
        self.candidate_list_size = candidate_list_size
        self.use_local_pheromone = use_local_pheromone
        self.rho_local           = rho_local
        self.callback            = callback

        self.w_inv_dist          = w_inv_dist
        self.w_connectivity      = w_connectivity
        self.w_successor_degree  = w_successor_degree
        self.w_city_balance      = w_city_balance

        self.fw_coverage         = fw_coverage
        self.fw_distance         = fw_distance
        self.fw_teleport         = fw_teleport
        self.fw_repetition       = fw_repetition
        self.fw_loop             = fw_loop
        self.fw_continuity       = fw_continuity
        self.fw_connectivity     = fw_connectivity
        self.fw_city_coverage    = fw_city_coverage
        self.fw_dead_end         = fw_dead_end
        self.fw_smoothness       = fw_smoothness

        self.alpha_init = alpha
        self.beta_init  = beta
        self.rho_init   = rho
        self.alpha      = alpha
        self.beta       = beta
        self.rho        = rho

        self.min_pheromone = 0.01
        self.max_pheromone = 100.0
        self.tau0          = 1.0

        self._stage_schedule = [
            (0.20, 0.8,  1.5, 0.30, 12, 1.0),
            (0.40, 1.3,  2.5, 0.22,  8, 0.9),
            (0.60, 1.8,  3.5, 0.16,  8, 0.8),
            (0.80, 2.4,  5.0, 0.11,  5, 0.7),
            (1.01, 3.0,  6.0, 0.08,  5, 0.6),
        ]

        self._restart_count  = 0
        self._dead_end_count = 0

        self._build_adjacency_and_candidates()
        self._init_pheromones()
        self._precompute_start_weights()
        self._precompute_heuristics()
        self._update_adaptive_candidate_list(0.0)

    def _build_adjacency_and_candidates(self):
        self.adj: Dict[int, List[int]] = {r["id"]: [] for r in ROUTES}
        for r in ROUTES:
            for s in ROUTES:
                if s["origin"] == r["dest"] and s["id"] != r["id"]:
                    self.adj[r["id"]].append(s["id"])
        self._full_candidates: Dict[int, List[int]] = {}
        for rid, successors in self.adj.items():
            sorted_succ = sorted(successors, key=lambda x: self._heuristic_raw(x), reverse=True)
            self._full_candidates[rid] = sorted_succ
        self.candidate_list: Dict[int, List[int]] = dict(self._full_candidates)

    def _init_pheromones(self):
        n = len(ROUTES)
        self.pheromone = [[self.max_pheromone] * n for _ in range(n)]

    def _precompute_start_weights(self):
        self.start_weights = [len(self.adj[r["id"]]) + 1 for r in ROUTES]

    def _precompute_heuristics(self):
        self._city_visits: Dict[str, int] = {}
        for r in ROUTES:
            self._city_visits[r["origin"]] = self._city_visits.get(r["origin"], 0) + 1
            self._city_visits[r["dest"]]   = self._city_visits.get(r["dest"], 0) + 1
        self._max_city_visits = max(self._city_visits.values()) if self._city_visits else 1
        self._heuristic_cache: Dict[int, float] = {}
        for r in ROUTES:
            self._heuristic_cache[r["id"]] = self._heuristic_raw(r["id"])

    def _heuristic_raw(self, route_id: int) -> float:
        r = ROUTES[route_id]
        dist     = r["dist"]
        inv_dist = 1.0 / dist if dist > 0 else 1.0
        out_deg  = len(self.adj.get(route_id, []))
        connectivity    = (out_deg + 1) / (len(ROUTES) / 5.0 + 1)
        succs           = self.adj.get(route_id, [])
        avg_succ_degree = sum(len(self.adj.get(s, [])) for s in succs) / len(succs) if succs else 0.0
        successor_degree= avg_succ_degree / (len(ROUTES) / 5.0 + 1)
        city_freq    = self._city_visits.get(r["origin"], 1) if hasattr(self, "_city_visits") else 1
        city_balance = 1.0 - (city_freq / (self._max_city_visits + 1)) if hasattr(self, "_max_city_visits") else 0.5
        return max(
            self.w_inv_dist * inv_dist
            + self.w_connectivity * connectivity
            + self.w_successor_degree * successor_degree
            + self.w_city_balance * city_balance,
            1e-9,
        )

    def _heuristic(self, route_id: int) -> float:
        return self._heuristic_cache.get(route_id, self._heuristic_raw(route_id))

    def _update_adaptive_parameters(self, iteration: int):
        progress = iteration / max(1, self.n_iterations - 1)
        for (thresh, alpha, beta, rho, cand_sz, ant_frac) in self._stage_schedule:
            if progress <= thresh:
                self.alpha  = alpha
                self.beta   = beta
                self.rho    = rho
                self.n_ants = max(self.n_ants_end, int(self.n_ants_start * ant_frac))
                break
        self._update_adaptive_candidate_list(progress)

    def _update_adaptive_candidate_list(self, progress: float):
        for (thresh, _, _, _, cand_sz, _) in self._stage_schedule:
            if progress <= thresh:
                sz = cand_sz; break
        else:
            sz = 5
        for rid in self._full_candidates:
            self.candidate_list[rid] = self._full_candidates[rid][:sz]

    def _look_ahead_score(self, current: int, candidate: int, visited_nodes: Set[int]) -> float:
        succs = self.adj.get(candidate, [])
        return sum(1 for s in succs if s not in visited_nodes and s != current)

    def _choose_next(self, current: int, visited_edges: Set[Tuple], visited_nodes: Set[int]) -> Tuple[int, bool]:
        cand = [c for c in self.candidate_list.get(current, [])
                if (current, c) not in visited_edges and c not in visited_nodes]
        if not cand:
            full = self.adj.get(current, [])
            cand = [c for c in full if (current, c) not in visited_edges and c not in visited_nodes]
        if not cand:
            full = self.adj.get(current, [])
            if full:
                cand_e = [c for c in full if (current, c) not in visited_edges]
                cand   = cand_e if cand_e else full
            else:
                self._dead_end_count += 1
                return -1, True
        return self._weighted_choice_lookahead(current, cand, visited_nodes), False

    def _weighted_choice_lookahead(self, current: int, pool: List[int], visited_nodes: Set[int]) -> int:
        weights = []
        for rid in pool:
            tau = self.pheromone[current][rid] ** self.alpha
            eta = self._heuristic(rid) ** self.beta
            la  = (self._look_ahead_score(current, rid, visited_nodes) + 1) ** 0.5
            weights.append(tau * eta * la)
        total = sum(weights)
        if total == 0:
            return random.choice(pool)
        return random.choices(pool, weights=[w / total for w in weights], k=1)[0]

    def _smart_restart_node(self) -> int:
        scores = []
        for r in ROUTES:
            rid     = r["id"]
            out_deg = len(self.adj.get(rid, []))
            h       = self._heuristic(rid)
            tau_sum = sum(self.pheromone[rid]) / len(ROUTES)
            scores.append((rid, out_deg * 0.4 + h * 0.4 + tau_sum * 0.2))
        scores.sort(key=lambda x: x[1], reverse=True)
        top_n   = max(3, len(scores) // 3)
        pool    = scores[:top_n]
        weights = [s for _, s in pool]
        return random.choices([r for r, _ in pool], weights=weights, k=1)[0]

    def _calculate_fitness(self, chain: List[int]) -> float:
        stats = self.validate_chain(chain)
        return (
            (stats["unique_routes"] / len(ROUTES)) * self.fw_coverage
            + stats["continuity_score"] * self.fw_continuity
            + stats["avg_branching"]    * self.fw_connectivity
            + stats["cities_covered"]   * self.fw_city_coverage
            + stats["chain_smoothness"] * self.fw_smoothness
            - stats["total_distance"]   * self.fw_distance
            - stats["teleports"]        * self.fw_teleport
            - (len(chain) - stats["unique_routes"]) * self.fw_repetition
            - stats["immediate_loops"]  * self.fw_loop
            - stats["dead_ends"]        * self.fw_dead_end
        )

    def _local_search(self, chain: List[int]) -> Tuple[List[int], float]:
        best_c = chain[:]
        best_f = self._calculate_fitness(best_c)
        improved = True
        attempts = 0
        max_attempts = 50
        while improved and attempts < max_attempts:
            improved = False
            n = len(best_c)
            for i in range(n):
                if attempts >= max_attempts: break
                attempts += 1
                node = best_c[i]
                rem  = best_c[:i] + best_c[i+1:]
                for j in range(len(rem)+1):
                    new_c = rem[:j] + [node] + rem[j:]
                    new_f = self._calculate_fitness(new_c)
                    if new_f > best_f:
                        best_c, best_f = new_c, new_f; improved = True; break
                if improved: break
            if improved: continue
            for i in range(n):
                if attempts >= max_attempts: break
                for j in range(i+1, n):
                    attempts += 1
                    new_c = best_c[:]
                    new_c[i], new_c[j] = new_c[j], new_c[i]
                    new_f = self._calculate_fitness(new_c)
                    if new_f > best_f:
                        best_c, best_f = new_c, new_f; improved = True; break
                if improved: break
            if improved: continue
            for i in range(n-1):
                if attempts >= max_attempts: break
                attempts += 1
                new_c = best_c[:]
                new_c[i], new_c[i+1] = new_c[i+1], new_c[i]
                new_f = self._calculate_fitness(new_c)
                if new_f > best_f:
                    best_c, best_f = new_c, new_f; improved = True; break
        return best_c, best_f

    def _build_chain(self) -> Tuple[List[int], float]:
        for attempt in range(4):
            start = (random.choices(range(len(ROUTES)), weights=self.start_weights, k=1)[0]
                     if attempt == 0 else self._smart_restart_node())
            if attempt > 0:
                self._restart_count += 1
            chain: List[int]          = [start]
            visited_edges: Set[Tuple] = set()
            visited_nodes: Set[int]   = {start}
            failed = False
            for _ in range(self.n_trips - 1):
                cur = chain[-1]
                nxt, restart = self._choose_next(cur, visited_edges, visited_nodes)
                if restart:
                    failed = True; break
                visited_edges.add((cur, nxt))
                chain.append(nxt)
                visited_nodes.add(nxt)
                if self.use_local_pheromone:
                    self.pheromone[cur][nxt] = max(
                        self.min_pheromone,
                        (1 - self.rho_local) * self.pheromone[cur][nxt] + self.rho_local * self.tau0,
                    )
            if not failed:
                return chain, self._calculate_fitness(chain)
        fallback = random.choices(range(len(ROUTES)), k=self.n_trips)
        return fallback, self._calculate_fitness(fallback)

    def _update_pheromones(self, elite: List[Tuple[List[int], float]], best: List[int]):
        n = len(ROUTES)
        for i in range(n):
            for j in range(n):
                self.pheromone[i][j] = max(self.min_pheromone, self.pheromone[i][j] * (1.0 - self.rho))
        if not elite:
            return
        total_rank = sum(range(1, len(elite)+1))
        for rank, (chain, _) in enumerate(elite):
            rank_weight = len(elite) - rank
            deposit = self.q * rank_weight / max(1.0, total_rank)
            for k in range(len(chain)-1):
                self.pheromone[chain[k]][chain[k+1]] = min(
                    self.max_pheromone, self.pheromone[chain[k]][chain[k+1]] + deposit)
        if best:
            for k in range(len(best)-1):
                self.pheromone[best[k]][best[k+1]] = min(
                    self.max_pheromone, self.pheromone[best[k]][best[k+1]] + self.q * 3.0)

    def _handle_stagnation(self, best_chain: Optional[List[int]], stagnation: int):
        n = len(ROUTES)
        best_edges: Set[Tuple[int,int]] = set()
        if best_chain:
            best_edges = {(best_chain[k], best_chain[k+1]) for k in range(len(best_chain)-1)}
        stage = (stagnation // self.stagnation_limit) % 3 + 1
        for i in range(n):
            for j in range(n):
                if (i, j) in best_edges: continue
                if stage == 1:
                    self.pheromone[i][j] = self.pheromone[i][j] * 0.7 + self.max_pheromone * 0.3
                elif stage == 2:
                    self.pheromone[i][j] = self.pheromone[i][j] * 0.4 + self.max_pheromone * 0.6
                else:
                    self.pheromone[i][j] = self.max_pheromone * 0.5
                self.pheromone[i][j] = min(self.max_pheromone, max(self.min_pheromone, self.pheromone[i][j]))

    def run(self) -> Tuple[List[int], float, List[float]]:
        best_chain:   Optional[List[int]] = None
        best_fitness: float = float("-inf")
        history:      List[float] = []
        stagnation:   int = 0
        self._restart_count  = 0
        self._dead_end_count = 0

        for iteration in range(self.n_iterations):
            self._update_adaptive_parameters(iteration)
            all_chains = [self._build_chain() for _ in range(self.n_ants)]
            all_chains.sort(key=lambda x: x[1], reverse=True)
            elite_cut  = max(1, int(len(all_chains) * 0.20))
            elite      = all_chains[:elite_cut]
            ib_chain, ib_fit = elite[0]
            opt_chain, opt_fit = self._local_search(ib_chain)
            if opt_fit > ib_fit:
                elite[0] = (opt_chain, opt_fit)
            top_chain, top_fit = elite[0]
            if top_fit > best_fitness:
                best_fitness = top_fit; best_chain = top_chain[:]; stagnation = 0
            else:
                stagnation += 1
            if stagnation > 0 and stagnation % self.stagnation_limit == 0:
                self._handle_stagnation(best_chain, stagnation)
            self._update_pheromones(elite, best_chain)
            history.append(best_fitness)
            if self.callback:
                self.callback(iteration + 1, self.n_iterations, best_fitness, best_chain)

        return best_chain, best_fitness, history

    def chain_to_trips(self, chain: List[int]) -> List[Trip]:
        return [Trip(trip_id=i, route_id=rid) for i, rid in enumerate(chain)]

    def validate_chain(self, chain: List[int]) -> Dict:
        if not chain:
            return {"total_trips":0,"unique_routes":0,"coverage_pct":0.0,"teleports":0,
                    "cities_covered":0,"total_distance":0,"immediate_loops":0,"dead_ends":0,
                    "continuity_score":0.0,"chain_smoothness":0.0,"avg_branching":0.0,
                    "avg_heuristic":0.0,"repeated_routes":0}
        teleports     = sum(1 for k in range(len(chain)-1)
                            if ROUTES[chain[k]]["dest"] != ROUTES[chain[k+1]]["origin"])
        unique_routes = len(set(chain))
        cities: Set[str] = set()
        for rid in chain:
            cities.add(ROUTES[rid]["origin"]); cities.add(ROUTES[rid]["dest"])
        total_dist   = sum(ROUTES[rid]["dist"] for rid in chain)
        imm_loops    = sum(1 for k in range(len(chain)-2) if chain[k] == chain[k+2])
        dead_ends    = sum(1 for k in range(len(chain)-1) if not self.adj.get(chain[k],[]))
        conn_pairs   = sum(1 for k in range(len(chain)-1) if chain[k+1] in self.adj.get(chain[k],[]))
        cont_score   = conn_pairs / max(1, len(chain)-1)
        if len(chain) > 1:
            dists    = [ROUTES[chain[k]]["dist"] for k in range(len(chain)-1)]
            avg_d    = sum(dists)/len(dists)
            variance = sum((d-avg_d)**2 for d in dists)/len(dists)
            smoothness = 1.0 / (1.0 + variance/10000.0)
        else:
            smoothness = 1.0
        avg_branching  = sum(len(self.adj.get(rid,[])) for rid in chain) / max(1,len(chain))
        avg_heuristic  = sum(self._heuristic(rid) for rid in chain) / max(1,len(chain))
        return {
            "total_trips":      len(chain),
            "unique_routes":    unique_routes,
            "coverage_pct":     round(unique_routes/len(ROUTES)*100, 1),
            "teleports":        teleports,
            "cities_covered":   len(cities),
            "total_distance":   total_dist,
            "immediate_loops":  imm_loops,
            "dead_ends":        dead_ends,
            "repeated_routes":  len(chain)-unique_routes,
            "continuity_score": round(cont_score, 3),
            "chain_smoothness": round(smoothness, 3),
            "avg_branching":    round(avg_branching, 2),
            "avg_heuristic":    round(avg_heuristic, 4),
        }

    def format_result(self, chain: List[int], fitness: float) -> str:
        lines = ["","="*52,"   ACO OPTIMIZED ROUTE CHAIN (56 Trips)","="*52]
        for i, rid in enumerate(chain, 1):
            r = ROUTES[rid]
            lines.append(f"  {i:>3}. {r['origin']:15s} → {r['dest']:15s}  ({r['dist']} km)")
        v = self.validate_chain(chain)
        lines += [
            "-"*52,
            f"  Total Trips        : {v['total_trips']}",
            f"  Unique Routes      : {v['unique_routes']} / {len(ROUTES)}",
            f"  Coverage           : {v['coverage_pct']}%",
            f"  Teleportasi        : {v['teleports']}",
            f"  Rute Berulang      : {v['repeated_routes']}",
            f"  Immediate Loops    : {v['immediate_loops']}",
            f"  Continuity Score   : {v['continuity_score']}",
            f"  Chain Smoothness   : {v['chain_smoothness']}",
            f"  Avg Branching      : {v['avg_branching']}",
            f"  Cities Covered     : {v['cities_covered']}",
            f"  Total Distance     : {v['total_distance']:,} km",
            f"  Fitness Score      : {fitness:.2f}",
            "-"*52,
            f"  Restarts           : {self._restart_count}",
            f"  Dead Ends          : {self._dead_end_count}",
            f"  Final α/β/ρ        : {self.alpha:.1f} / {self.beta:.1f} / {self.rho:.2f}",
            "="*52,
        ]
        return "\n".join(lines)