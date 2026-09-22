Building a practical scheduling system for intercity buses gets messy fast. You have to figure out travel routes, keep track of where every bus is parked, match up drivers and conductors, avoid scheduling overlaps, and make sure maintenance happens before anything breaks. Doing all of this by hand quickly turns into an NP-hard combinatorial headache.

SmartBus Scheduler is a web app built to solve this. Instead of brute-forcing schedules, it uses a two-stage hybrid AI approach to automatically map out efficient routes and build a solid, conflict-free weekly schedule.

Hybrid AI Architecture
1. Ant Colony Optimization (ACO): The system treats cities like connected nodes on map. Using pheromone trails and distance heuristics, ACO figures out the best travel paths and sequences for the buses to run.
2. Particle Swarm Optimization (PSO): Once the routes are set, PSO takes over the heavy lifting of scheduling. It assigns specific buses, drivers, and conductors to time slots across a 40-trip weekly plan, constantlyy tweaking things to cut down on dead routes and avoid scheduling conflicts.

Core Features
- Dashboard: Gives quick snapshot of active buses, total routes, available crew, and the current status of optimization engine.
- Data Management: Clean forms to manage master data for buses, drivers, conductors, and routes.
- AI Engine Panel: Trigger buttons to run the workflow step-by-step.
- Result Viewer & Analytics: Breaks down the final 1-week schedule into readable tables, timeline views for buses and crews, city graph visualizers, and a fitness score tracking system performance.
