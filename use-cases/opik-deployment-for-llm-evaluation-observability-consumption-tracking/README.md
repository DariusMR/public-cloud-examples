This project is linked to a reference architecture that illustrates the self-hosting of **Opik** on OVHcloud **Managed Kubernetes Service** (MKS) to capture every Large Language Model request as a trace (model, tokens, cost, ...). All of this is deployed within your own infrastructure, supported by OVHcloud’s managed MySQL, Valkey as well as S3-compatible Object Storage. 

## Prerequisites

Before you begin, ensure you have:
- An OVHcloud Public Cloud account
- An OpenStack user with the Administrator role
- An AI Endpoints API key
- A domain name you can point at a load balancer
- `kubectl` installed and `helm` installed (at least version 3.x)

## How to use the project

Follow the different steps of this [architecture guide](docs/deploy-opik-ovhcloud-mks.en.md) to maintain control over all data relating to requests, outputs and costs for LLMaaS-type platforms, whilst remaining within an infrastructure that you control.

![image](docs/opik-architecture-overview.jpg)