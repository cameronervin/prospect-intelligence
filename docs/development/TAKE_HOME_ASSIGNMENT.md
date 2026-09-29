# Deployed Engineer, Professional Services: Take-Home Assignment

> Source: [Notion assignment](https://mirror-feeling-d80.notion.site/Deployed-Engineer-Professional-Services-Take-Home-Assignment-3cd808527b1780d7909fc380cd8c1ebb?pvs=143)

## Background

This role works directly with enterprise engineering teams to advise on and co-build production agent systems. That means the day-to-day is a mix of hands-on building, sound architectural judgment, and the ability to explain and defend technical decisions to both engineers and business stakeholders.

This assignment is designed to test exactly that: your ability to design a modern agent system, build it, evaluate it rigorously, and communicate your reasoning clearly.

---

## Your Task

You'll be briefing a customer stakeholder (played by your interviewers) on an initial agent system you’ve built for them. They need to decide whether it's worth taking further.

Pick a domain and specific problem to solve that you believe represents real enterprise complexity (e.g. customer support automation, internal ops workflow, research/document synthesis, etc).

Architect and build an MVP using modern agent design patterns, evaluate it thoroughly, and lay out what it would take to reach production, so your stakeholder has what they need to decide.

**Solution Requirements:**

- **Reflects real enterprise complexity and uses modern agent design patterns.** Not a simple demo agent making a single tool call.
- **Incorporate human-in-the-loop.** A point where a human can intervene, review, or approve before the agent proceeds, where it makes sense.
- **Integrate with external APIs or data sources** as needed for your domain.
- **A comprehensive evaluation approach** covering dataset design, offline validation, and online monitoring considerations. You should prioritize and implement at least one evaluation metric that you deem most important at the MVP stage, and run at least one experiment in LangSmith to quantify your agent’s performance. A documented plan is enough for the rest of the evaluation approach (no need to implement every component or metric), but it should be well defined and thorough. You should be able to speak to any part if asked.

**Stack:**

- Python
- LangChain OSS ecosystem (LangChain, LangGraph, and/or Deep Agents)
- LangSmith for evaluation and tracing. Free LangSmith account: [smith.langchain.com](http://smith.langchain.com)

---

## What to Prepare

### 1. Code repository

Your agent system, in a state you're comfortable walking us through. This doesn't need to be production-hardened. We're looking for strong signal in your build quality, methodology, and judgment, not a perfectly polished product.

### 2. Presentation + live demo

A slide deck, plus a live walkthrough of your system in action and your LangSmith evals. Present as if we are a team of customer stakeholders. At a minimum, you should cover:

- **Problem & approach:** What you're building, why this architecture, and why it reflects real enterprise complexity.
- **Trade-offs:** What alternatives you considered, and why you landed here.
- **Evaluation & results:** Your holistic evaluation approach, what you measured (or would measure) and why, your results, and what those results tell a stakeholder deciding whether to continue this project or not.
- **Path to production (required to explain, optional to build):** Memory/state scoping, auth & multi-tenancy, failure recovery, guardrails, plus anything else you deem relevant. Implementing any of it is a bonus, not an expectation.

### 3. Friction log

Any challenges, limitations, or rough edges you hit with LangChain, LangGraph, Deep Agents, or LangSmith throughout the process.

---

## The Live Session

**60 minutes total.** Your interviewers play the customer stakeholder deciding whether to continue building this project.

- **Presentation (~45 min):** Walk us through the problem you're solving, what you built, your decisions, and your results. Expect questions that probe implementation detail and questions that test whether you can translate it into business outcomes.
- **Q&A (~15 min):** We'll push back in character, and ask what you'd do differently at scale or under different constraints.

---

## What We're Looking For

**Technical depth:** Do you understand what you built well enough to defend it? Can you explain why it works the way it does, not just how to use it?

**Problem & architecture judgment:** Did you choose a problem and an approach that reflects real enterprise complexity? Can you articulate the trade-offs you considered?

**Evaluation rigor:** Is your approach to measuring quality sound, comprehensive, and well-reasoned, including what you chose to evaluate and how you implemented it? Does your evaluation approach cover both before-deployment validation and after-deployment monitoring? Did you prioritize the metric that gives the clearest signal at the MVP stage, and do your conclusions follow logically from your results?

**Production judgment:** Even though implementation isn't required, do you show real operational thinking about running this in production (memory scoping, auth/multi-tenancy, failure recovery, guardrails, scaling, etc)?

**Communication:** Can you move between engineer-level detail and business-level framing in the same conversation?

**Adaptability:** How do you handle pushback, unexpected questions, or being asked to reconsider a decision on the spot?

---

## Logistics

- **Time:** ~1 week. Not looking for production-ready, no need to over-engineer things.
- **Share ahead of the live session:** Your code repository, presentation deck, and friction log. Once shared, we'll schedule the live session shortly after.
- **Resources:** use whatever you need. We care what you do with it, not whether you found it yourself.
  - [Open-source Documentation](https://docs.langchain.com/build-overview)
  - [LangSmith Documentation](https://docs.langchain.com/langsmith/home)
  - [Chat LangChain Agent](https://chat.langchain.com/)
  - [LangChain Academy](https://academy.langchain.com/)
