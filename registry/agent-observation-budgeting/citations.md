# Citations

Every method rule this skill encodes traces to a source here.

## [read-more-think-more]

- Title: Read More, Think More: Revisiting Observation Reduction for Web Agents
- Authors: Masafumi Enomoto, Ryoma Obara, Haochen Zhang, Masafumi Oyamada
- Venue and year: arXiv preprint, 2026
- Identifier: arXiv:2604.01535v1
- Method rule extracted: Adaptively select the observation representation from the model's capability and its thinking token budget, rather than fixing one representation for every model and every step.
- Objective supported: sufficiency: give the model enough to reason with

## [lineretriever-planning-aware-observation]

- Title: LineRetriever: Planning-Aware Observation Reduction for Web Agents
- Authors: Imene Kerboua, Sahar Omidi Shayegan, Megh Thakkar, Xing Han Lu, Massimo Caccia, Veronique Eglin
- Venue and year: arXiv preprint, 2025
- Identifier: arXiv:2507.00210v1
- Method rule extracted: Retrieve only the lines the current plan needs, judged against the planning horizon rather than against the page. Reducing by relevance to the page drops lines the planner still required.
- Objective supported: sufficiency: keep what the plan will need next
