"""
providers/cloud/real_aws.py
Provider AWS REAL — usa boto3 para buscar dados reais de custo e inventário.

Para ativar:
  1. pip install boto3
  2. Configurar credenciais: aws configure  OU  variável AWS_PROFILE
  3. Definir no .env: CLOUD_AWS_MODE=real

Este módulo é um adapter entre a AWS SDK (boto3) e a interface CloudProvider.
A lógica dos agentes não muda — apenas este arquivo é trocado.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

from providers.cloud.base import CloudProvider, CloudResource
from logger import get_logger

log = get_logger("real_aws")


class RealAWSProvider(CloudProvider):
    """
    Busca recursos e custos reais da AWS via boto3.

    Serviços consultados:
      - Cost Explorer  -> custos por recurso/serviço
      - EC2            -> instâncias compute
      - S3             -> buckets com metadados de segurança
      - RDS            -> bancos de dados

    Requer: boto3, credenciais AWS configuradas.
    """

    def __init__(self) -> None:
        try:
            import boto3

            self._session = boto3.Session(
                profile_name=os.getenv("AWS_PROFILE"),
                region_name=os.getenv("AWS_DEFAULT_REGION", "us-east-1"),
            )
            log.info(
                "real_aws_init", region=os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            )
        except ImportError:
            raise ImportError(
                "boto3 não instalado. Execute: pip install boto3\n"
                "Depois configure credenciais com: aws configure"
            )

    def provider_name(self) -> str:
        return "aws"

    def get_resources(self) -> list[CloudResource]:
        resources: list[CloudResource] = []
        resources.extend(self._get_ec2_instances())
        resources.extend(self._get_s3_buckets())
        resources.extend(self._get_rds_instances())
        log.info("real_aws_fetch_complete", count=len(resources))
        return resources

    # EC2

    def _get_ec2_instances(self) -> list[CloudResource]:
        ec2 = self._session.client("ec2")
        ce = self._session.client("ce", region_name="us-east-1")

        resources: list[CloudResource] = []
        instances: list[dict] = []

        paginator = ec2.get_paginator("describe_instances")

        for page in paginator.paginate():
            for reservation in page.get("Reservations", []):
                for instance in reservation.get("Instances", []):
                    instances.append(instance)

        total_cost = self._get_costs_by_service(
            "Amazon Elastic Compute Cloud - Compute", ce
        )

        count = len(instances)
        cost_per_instance = total_cost / count if count else 0.0

        # 4. Montar recursos
        for instance in instances:
            instance_id = instance["InstanceId"]
            state = instance["State"]["Name"]

            tags = [t["Value"] for t in instance.get("Tags", [])]

            resources.append(
                CloudResource(
                    {
                        "provider": "aws",
                        "service_type": "compute",
                        "service_name": "ec2",
                        "region": instance.get("Placement", {}).get(
                            "AvailabilityZone", ""
                        ),
                        "resource_id": instance_id,
                        "cost": cost_per_instance,
                        "is_idle": state != "running",
                        "is_public": bool(instance.get("PublicIpAddress")),
                        "has_encryption": True,
                        "has_access_control": True,
                        "tags": tags,
                        "schema_hint": [],
                    }
                )
            )

        log.debug("real_aws_ec2", count=len(resources), total_cost=total_cost)
        return resources

    # S3

    def _get_s3_buckets(self) -> list[CloudResource]:
        s3 = self._session.client("s3")
        ce = self._session.client("ce", region_name="us-east-1")
        resources = []

        buckets = s3.list_buckets().get("Buckets", [])

        total_cost = self._get_costs_by_service("Amazon Simple Storage Service", ce)

        count = len(buckets)
        cost_per_bucket = total_cost / count if count else 0.0

        for bucket in buckets:
            name = bucket["Name"]
            is_public = self._is_s3_bucket_public(s3, name)
            has_encrypt = self._s3_has_encryption(s3, name)
            has_acl = self._s3_has_access_control(s3, name)

            resources.append(
                CloudResource(
                    {
                        "provider": "aws",
                        "service_type": "storage",
                        "service_name": "s3",
                        "region": self._get_bucket_region(s3, name),
                        "resource_id": f"s3://{name}",
                        "cost": cost_per_bucket,
                        "is_idle": False,
                        "is_public": is_public,
                        "has_encryption": has_encrypt,
                        "has_access_control": has_acl,
                        "tags": self._get_s3_tags(s3, name),
                        "schema_hint": [],
                    }
                )
            )

        log.debug("real_aws_s3", count=len(resources))
        return resources

    # RDS

    def _get_rds_instances(self) -> list[CloudResource]:
        rds = self._session.client("rds")
        ce = self._session.client("ce", region_name="us-east-1")

        resources: list[CloudResource] = []
        instances: list[dict] = []

        paginator = rds.get_paginator("describe_db_instances")

        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                instances.append(db)

        total_cost = self._get_costs_by_service(
            "Amazon Relational Database Service", ce
        )

        count = len(instances)
        cost_per_db = total_cost / count if count else 0.0

        for db in instances:
            db_id = db["DBInstanceIdentifier"]

            resources.append(
                CloudResource(
                    {
                        "provider": "aws",
                        "service_type": "database",
                        "service_name": "rds",
                        "region": db.get("AvailabilityZone", ""),
                        "resource_id": db_id,
                        "cost": cost_per_db,
                        "is_idle": db.get("DBInstanceStatus") != "available",
                        "is_public": db.get("PubliclyAccessible", False),
                        "has_encryption": db.get("StorageEncrypted", False),
                        "has_access_control": len(db.get("VpcSecurityGroups", [])) > 0,
                        "tags": [],
                        "schema_hint": [],
                    }
                )
            )

        log.debug("real_aws_rds", count=len(resources), total_cost=total_cost)
        return resources

    def _get_costs_by_service(self, service_name: str, ce_client: Any) -> float:
        try:
            end = datetime.now(timezone.utc).date()
            start = end - timedelta(days=30)

            response = ce_client.get_cost_and_usage(
                TimePeriod={"Start": str(start), "End": str(end)},
                Granularity="MONTHLY",
                Metrics=["BlendedCost"],
                Filter={"Dimensions": {"Key": "SERVICE", "Values": [service_name]}},
            )

            total = 0.0
            for result in response.get("ResultsByTime", []):
                amount = float(result["Total"]["BlendedCost"]["Amount"])
                total += amount

            return total

        except Exception as exc:
            log.warning("cost_explorer_error", service=service_name, error=str(exc))
            return 0.0

    def _is_s3_bucket_public(self, s3: Any, bucket: str) -> bool:
        try:
            acl_status = s3.get_public_access_block(Bucket=bucket)
            cfg = acl_status["PublicAccessBlockConfiguration"]
            return not (cfg.get("BlockPublicAcls") and cfg.get("BlockPublicPolicy"))
        except Exception:
            return True  # assume público se não conseguir verificar

    def _s3_has_encryption(self, s3: Any, bucket: str) -> bool:
        try:
            s3.get_bucket_encryption(Bucket=bucket)
            return True
        except s3.exceptions.ClientError:
            return False
        except Exception:
            return False

    def _s3_has_access_control(self, s3: Any, bucket: str) -> bool:
        try:
            policy = s3.get_bucket_policy_status(Bucket=bucket)
            return not policy["PolicyStatus"].get("IsPublic", True)
        except Exception:
            return False

    def _get_bucket_region(self, s3: Any, bucket: str) -> str:
        try:
            loc = s3.get_bucket_location(Bucket=bucket)
            return loc.get("LocationConstraint") or "us-east-1"
        except Exception:
            return "unknown"

    def _get_s3_tags(self, s3: Any, bucket: str) -> list[str]:
        try:
            resp = s3.get_bucket_tagging(Bucket=bucket)
            return [f"{t['Key']}={t['Value']}" for t in resp.get("TagSet", [])]
        except Exception:
            return []
