# AWS Deployment Runbook

The repository is ready for the next AWS live-deployment phase. AWS infrastructure and credentials must be provisioned separately.

## Recommended Architecture

- Route 53 domain, ACM TLS certificate, and Application Load Balancer.
- ECS Fargate service running the Docker image from ECR.
- RDS PostgreSQL in private subnets with automated backups.
- EFS mounted at `/app/media` for current file uploads.
- Secrets Manager or SSM Parameter Store for all production `SIYA_*` values.
- CloudWatch Logs and alarms; ALB health check path `/health/`.

Do not run production with SQLite or ephemeral container media storage.

## Required Environment

```text
SIYA_ENV=production
SIYA_DEBUG=false
SIYA_SECRET_KEY=<long-random-secret>
SIYA_ALLOWED_HOSTS=crm.example.com
SIYA_CSRF_TRUSTED_ORIGINS=https://crm.example.com
SIYA_DATABASE_URL=postgresql://USER:PASSWORD@RDS_HOST:5432/DB_NAME
SIYA_EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
SIYA_EMAIL_HOST=<smtp-host>
SIYA_EMAIL_PORT=465
SIYA_EMAIL_USE_SSL=true
SIYA_EMAIL_HOST_USER=<smtp-user>
SIYA_EMAIL_PASSWORD=<smtp-password>
SIYA_DEFAULT_FROM_EMAIL=Siya Real Build <noreply@example.com>
SIYA_SECURE_SSL_REDIRECT=true
SIYA_SESSION_COOKIE_SECURE=true
SIYA_CSRF_COOKIE_SECURE=true
SIYA_SECURE_HSTS_SECONDS=31536000
SIYA_SECURE_HSTS_INCLUDE_SUBDOMAINS=true
```

Enable `SIYA_SECURE_HSTS_PRELOAD=true` only after confirming every current and future subdomain will always support HTTPS. HSTS preload is intentionally not forced by the application.

## Release Sequence

1. Build and push the image to ECR.
2. Run one-off ECS task: `python manage.py migrate`.
3. Run one-off ECS task: `python manage.py check --deploy`.
4. Deploy/update the ECS service.
5. Confirm ALB `/health/` returns HTTP 200.
6. Verify owner login, email OTP, property create, plot booking, payment, visit, and document workflows.
7. Configure alarms for target health, HTTP 5xx, CPU/memory, and RDS storage/connections.
8. Perform an RDS restore test and EFS backup restore test before launch approval.

## Automated Bootstrap

Prerequisites on the deployment workstation: AWS CLI v2, Docker, PowerShell, authenticated AWS credentials, an ACM certificate, and the intended production domain.

1. Copy `deploy/aws/parameters.example.json` to a private parameter file outside Git and replace every placeholder.
2. Run:

```powershell
.\deploy\aws\deploy.ps1 `
  -Region ap-south-1 `
  -Repository siya-real-build `
  -StackName siya-real-build-production `
  -ParameterFile C:\secure\siya-production-parameters.json
```

The CloudFormation stack provisions VPC networking, ECS Fargate, RDS PostgreSQL, EFS media storage, Secrets Manager, ALB HTTPS listener, CloudWatch logs/alarms, and SNS email alerts. The deployment script builds/pushes the image, deploys the stack, runs migrations and deployment checks as one-off tasks, then waits for service stability.

After the first deployment, create the Route 53 alias record pointing the production hostname to the stack's `LoadBalancerDnsName` output.

## GitHub Production Deploy

The `Deploy AWS` workflow supports later image releases after the initial stack exists.

Configure GitHub production environment:

- Secret: `AWS_DEPLOY_ROLE_ARN`
- Variables: `AWS_REGION`, `ECR_REPOSITORY`, `ECS_CLUSTER`, `ECS_SERVICE`, `ECS_TASK_FAMILY`

Use an AWS IAM OIDC role restricted to this repository and production environment. Trigger the workflow manually and enter `deploy-production`.

## Launch Gate

- `check --deploy` passes under the real production environment.
- RDS migrations and backup restore drill pass.
- HTTPS/domain/email delivery pass.
- Media persists across task replacement.
- CloudWatch alarms and operational ownership are confirmed.
