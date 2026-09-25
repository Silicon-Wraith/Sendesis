# Sendesis

**An open-source runtime for assembling and coordinating teams of
specialized AI experts.**

> **Status:** Early development. Sendesis is currently being designed
> and prototyped. APIs, architecture, and concepts described here will
> evolve.

## The Idea

Today's AI development tools are extraordinarily capable, but most still
revolve around a single agent or model attempting to perform many
different kinds of work.

Real engineering teams don't work that way.

Architects design. Engineers implement. Security specialists look for
vulnerabilities. Test engineers attack assumptions. Reviewers
independently evaluate work. Specialists disagree, challenge one
another, and converge on decisions supported by evidence.

Sendesis explores a different model:

**Don't build a better AI agent. Build a team.**

A Sendesis workflow assembles specialized **roles** to perform a task.
Each role defines the expertise, responsibilities, context,
capabilities, constraints, and expected outputs required of that
participant.

Roles can be performed by different models from different providers. The
model filling a role is an implementation detail rather than part of the
role's identity.

``` text
Role != Model
Workflow != CLI
Policy != Routing
Model Routing != Compute Routing
```

A Security Reviewer remains a Security Reviewer whether the role is
currently filled by an Anthropic model, an OpenAI model, or a qualified
open-source model running locally.

## Why Sendesis?

Different models have different strengths, costs, latency
characteristics, context limits, and failure modes.

Using several models is easy.

Making them behave like an effective team is not.

Sendesis provides the organizational layer:

``` text
                    Workflow
                       |
        +--------------+--------------+
        |              |              |
     Expert         Expert         Expert
      Role           Role           Role
        |              |              |
        +------- independent work ----+
                       |
                   Challenge
                       |
                    Evidence
                       |
               Consensus / Dissent
                       |
                  Adjudication
                       |
                     Result
```

The interesting problem isn't simply routing prompts to models.

It is defining **who should participate, what each participant is
responsible for, what knowledge and capabilities they receive, how their
work is evaluated, how disagreement is handled, and when the team has
produced an acceptable result.**

That is the problem Sendesis intends to solve.

## Roles

Roles are reusable definitions of expertise.

A software-engineering team might contain:

``` text
Software Architect
Security Reviewer
Implementation Engineer
Test Engineer
Performance Reviewer
Code Reviewer
```

Users can define additional roles appropriate to their projects and
compose them into reusable workflows.

A role may define:

-   expertise and responsibilities
-   instructions and behavioral constraints
-   required project context
-   available tools and permissions
-   input and output contracts
-   definition of done
-   model capability requirements
-   qualification tests

Roles are intentionally extensible. Sendesis provides the runtime and
contracts; users determine the expertise their teams require.

## Workflows

Roles provide expertise.

**Workflows organize expertise.**

A workflow defines which roles participate, when they execute, what
information they may share, how findings move between phases, and what
constitutes completion.

For example:

``` text
Architecture Review

    Independent Analysis
        |
        +-- Software Architect
        +-- Security Reviewer
        +-- Test Strategist
        |
        v
    Cross-Challenge
        |
        v
    Evidence Verification
        |
        v
    Adjudication
        |
        v
    Decision
```

Independence is intentional.

Reviewers may initially be prevented from seeing one another's
conclusions so that agreement represents independent analysis rather
than model conformity.

Disagreement is not failure.

Unresolved dissent can itself be an important output.

## Model Qualification

Sendesis treats the question:

> **Can this model perform this role?**

as an empirical question rather than an assumption.

Roles may provide qualification suites against which candidate models
can be evaluated.

A model that satisfies the qualification requirements becomes eligible
to fill that role. Routing policy can then select among qualified models
according to factors such as:

-   capability
-   availability
-   cost
-   latency
-   context requirements
-   model diversity
-   local or cloud execution policy

This preserves an important abstraction:

``` text
Role = durable capability contract
Model = replaceable implementation
```

As models improve, the models filling a role can change without changing
the workflow.

## Model Independence

Sendesis is being designed around heterogeneous inference.

A team may contain experts backed by:

-   Anthropic models
-   OpenAI models
-   open-source models
-   locally hosted models

Different roles in the same workflow may deliberately use models from
different families.

This allows Sendesis to take advantage of differing model capabilities
and reduces dependence on any single model provider.

It can also provide genuine diversity during independent review rather
than simply asking multiple instances of the same model the same
question.

Model selection and inference routing remain separate from the semantics
of the role itself.

## Policy and Routing

Sendesis separates **deciding what should happen** from **executing that
decision**.

``` text
Role / Workflow
      |
      v
Policy / Judge
      |
      |  Which qualified model should perform this task?
      v
Model Routing
      |
      +---------- Cloud ----------> Provider
      |
      +---------- Local
                     |
                     v
               Compute Routing
                     |
                     v
              Local Inference
```

The policy layer can consider the role, workflow state, model
qualifications, availability, cost, diversity requirements, and other
runtime constraints.

The routing layer does not define engineering policy. It carries out the
routing decision.

This distinction is deliberate.

## Model Routing

[NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard) is
currently being evaluated as the model-routing fabric for Sendesis.

Switchyard provides routing across heterogeneous model providers and
supports custom classification and routing policies.

Sendesis treats Switchyard as infrastructure rather than as an
application-level abstraction.

The Sendesis policy layer determines the requirements of the task.
Switchyard provides the mechanism for resolving and executing the
resulting inference route.

The integration will remain behind a Sendesis-owned interface so the
routing implementation remains replaceable.

## Local and Distributed Inference

Local models are first-class participants in the Sendesis architecture.

A role should not need to know whether its inference is being performed
by a cloud provider or by a model running on local hardware.

For a single local machine:

``` text
Sendesis
    |
    v
Switchyard
    |
    v
Local Inference
```

As additional local compute becomes available, [NVIDIA Personal AI
Router (PAIR)](https://github.com/NVIDIA/Personal-AI-Router) is being
evaluated as an optional compute-routing layer:

``` text
Sendesis
    |
    v
Policy / Judge
    |
    v
Switchyard
    |
    v
PAIR
    |
    +-------- Node A
    |
    +-------- Node B
    |
    +-------- Node C
```

The responsibilities remain separate:

``` text
Sendesis Policy     -> Which qualified model should perform the task?
Switchyard          -> How should the request reach that model?
PAIR                -> Which eligible local machine should execute it?
Inference Engine    -> Execute the model.
```

Neither Switchyard nor PAIR defines Sendesis roles or workflows.

## Project Knowledge

Expertise without context is limited.

Sendesis is being designed so roles can consume persistent project
knowledge through pluggable context providers.

For software development, that knowledge might include:

``` text
requirements
architecture
ADRs
source documentation
coding standards
API contracts
previous findings
technical decisions
known constraints
```

Roles retrieve the project context relevant to the work they are
performing rather than requiring every workflow to provide the entire
project history.

This allows participating experts to operate with a shared understanding
of the system while keeping the role and context systems independently
extensible.

## Context Is Not Enforcement

Providing a model with instructions does not guarantee that those
instructions will be followed.

Sendesis therefore distinguishes three related responsibilities:

### Convey

Provide the role with the knowledge, requirements, constraints, and
project context necessary to perform its work.

### Constrain

Restrict capabilities where appropriate rather than relying exclusively
on instructions.

A reviewer that should not modify source code should not merely be told
not to modify it. Where supported by the execution environment, it
should not be given that capability.

### Verify

Evaluate outputs mechanically where possible.

Structured output contracts, schemas, qualification tests, workflow
gates, and other verification mechanisms can establish whether the
result satisfies the requirements of the role.

``` text
Convey
   +
Constrain
   +
Verify
   =
Controlled execution
```

Context provides understanding.

It does not provide enforcement.

## Client Independence

A Sendesis workflow should not depend on the development client that
initiated it.

The same workflow should eventually be invokable from different
environments:

``` text
CLI
IDE
Coding Agent
CI Pipeline
API
Automation
     |
     v
 Sendesis
     |
     v
Same Roles
Same Workflows
Same Policies
Same Project Knowledge
```

This allows developers and teams to use their preferred tools while
sharing the same virtual engineering organization.

## Evidence, Consensus, and Dissent

Consensus is not simply majority voting.

Several models producing the same answer does not establish that the
answer is correct.

Sendesis workflows can instead reason over structured findings and
supporting evidence.

A finding might contain:

``` text
finding
    id
    category
    claim
    evidence
    severity
    confidence
    recommendation
    assumptions
```

Other roles can independently confirm, reject, reproduce, or challenge
that finding.

A workflow can then distinguish between:

``` text
confirmed
disputed
unverified
rejected
blocking
non-blocking
```

The goal is not to force agreement.

The goal is to make agreement and disagreement **visible, attributable,
and useful**.

## Design Principles

Sendesis is being developed around several principles.

### Roles are not models

Expertise must survive model churn.

### Workflows are not clients

A workflow should work regardless of whether it was initiated from a
CLI, IDE, CI pipeline, API, or another agent.

### Policy is not routing

Sendesis decides what should happen. Routing infrastructure carries out
that decision.

### Model routing is not compute routing

Selecting the appropriate model and selecting the physical resource that
executes local inference are separate responsibilities.

### Context is not enforcement

Instructions convey expectations. Capabilities constrain behavior.
Verification establishes whether requirements were satisfied.

### Qualification beats assumption

Models earn eligibility for roles through measurable performance rather
than reputation or intuition.

### Infrastructure is replaceable

Model routers, compute routers, inference engines, model providers,
context stores, and development clients live behind Sendesis-owned
contracts.

### Diversity is useful

Independent models with different strengths and failure modes can be
more valuable than multiple instances of the same model agreeing with
one another.

### Disagreement is information

Consensus mechanisms should expose unresolved differences rather than
hide them.

### The runtime owns the abstractions

External infrastructure may implement important capabilities, but
Sendesis owns the concepts that define its behavior:

``` text
Roles
Workflows
Qualification
Policy
Context
Evidence
Consensus
Adjudication
```

## Architecture

The current architectural direction is:

``` text
                         Sendesis

              +---------------------------+
              |      Workflow Plane       |
              |                           |
              | Roles                     |
              | Workflows                 |
              | Challenge                 |
              | Consensus                 |
              | Adjudication              |
              +-------------+-------------+
                            |
              +-------------v-------------+
              |       Context Plane       |
              |                           |
              | Project knowledge         |
              | Requirements              |
              | Architecture              |
              | History                   |
              +-------------+-------------+
                            |
              +-------------v-------------+
              |       Policy Plane        |
              |                           |
              | Qualification             |
              | Model eligibility         |
              | Runtime policy            |
              | Judge                     |
              +-------------+-------------+
                            |
              +-------------v-------------+
              |    Model Routing Plane    |
              |                           |
              |        Switchyard         |
              +------+------+-------------+
                     |      |
                  Cloud    Local
                     |      |
                     |      v
                     |   +-----------------+
                     |   | Compute Plane   |
                     |   |                 |
                     |   |      PAIR       |
                     |   +---+----+----+---+
                     |       |    |    |
                     |      GPU  GPU  GPU
                     |
               Model Providers
```

The important boundaries are intentional.

No individual provider, router, inference engine, context
implementation, or development client should become Sendesis itself.

## Current Status

Sendesis is at the beginning.

The initial work is focused on validating the core abstractions through
software-engineering workflows:

-   extensible expert roles
-   reusable workflows
-   heterogeneous model execution
-   model qualification
-   deterministic policy and routing
-   persistent project context
-   independent review
-   evidence-based findings
-   challenge and adjudication
-   consensus with explicit dissent

The immediate objective is not to build a large collection of agents.

It is to establish a small, durable runtime capable of coordinating
specialized AI experts in a repeatable engineering process.

The project is being developed in the open.

------------------------------------------------------------------------

## Name

**Sendesis** *(sen-DEE-sis)*

*Assemble expertise.*
