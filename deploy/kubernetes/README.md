# Kubernetes deployment example

This is a platform-neutral Kustomize base for the production image. It does not
create PostgreSQL, Redis, an ingress controller, a certificate, or a secret
manager. Use managed services and your platform's ingress/Gateway integration.

## Before applying

1. Publish the reviewed image and replace the image tag with an immutable tag or
   digest.
2. Review `configmap.yaml`; it contains safe defaults, not your production
   domains or traffic limits.
3. Create the secret from a protected local file or your secret manager. Do not
   commit a populated secret manifest:

   ```bash
   cp deploy/kubernetes/secret.example.env production.env
   # Replace every placeholder in production.env.
   kubectl -n fastapi-production-api create secret generic \
     fastapi-production-api-secrets --from-env-file=production.env
   ```

4. Label only namespaces allowed to reach the API (for example your ingress and
   monitoring namespaces):

   ```bash
   kubectl label namespace ingress-nginx \
     access.fastapi-production-api/ingress=true
   ```

   The NetworkPolicy requires a CNI that enforces NetworkPolicy. It deliberately
   does not restrict egress because database, Redis, SMTP, OIDC, and telemetry
   destinations are platform-specific. Add an egress policy after identifying
   their exact namespaces, CIDRs, and ports.

## Release sequence

For a first install, create the namespace, ServiceAccount, and ConfigMap before
the migration Job. Do not create the Deployment until the migration finishes:

```bash
kubectl apply -f deploy/kubernetes/namespace.yaml \
  -f deploy/kubernetes/serviceaccount.yaml \
  -f deploy/kubernetes/configmap.yaml
```

Copy `migration-job.example.yaml`, replace its image placeholder, then create
it once for the release:

```bash
kubectl create -f migration-job.yaml
kubectl -n fastapi-production-api wait --for=condition=complete job/<job-name> --timeout=5m
kubectl -n fastapi-production-api rollout status deployment/fastapi-production-api
```

After a successful migration, render and apply the base with an immutable image
reference. For later releases, perform the same migration Job before updating
the Deployment image:

```bash
kustomize edit set image \
  fastapi-production-api=ghcr.io/houngdev/fastapi-production-api@sha256:<digest>
kubectl apply -k deploy/kubernetes
```

The HPA requires metrics-server or another compatible `metrics.k8s.io`
provider. Configure your ingress/Gateway separately to expose the Service, keep
`/metrics` restricted to monitoring, and set `FORWARDED_ALLOW_IPS` only after
identifying the direct proxy peers seen by the Pod.
