#!/usr/bin/env python3
"""
CDK stack to import an existing TLS certificate into AWS Certificate Manager (ACM).

ACM does not auto-renew imported certificates. Plan to re-import before expiry or switch
to ACM-issued certificates with DNS validation (see super-fiesta/stacks/acm_certificate/).

Supported certificate sources (first match wins):
1. Secrets Manager JSON secret (recommended for production)
2. Local PEM files via CDK context (-c certificate_path=..., etc.)

Secrets Manager secret format (JSON):
{
  "certificate": "-----BEGIN CERTIFICATE-----\\n...",
  "privateKey": "-----BEGIN PRIVATE KEY-----\\n...",
  "certificateChain": "-----BEGIN CERTIFICATE-----\\n..."   // optional
}

Usage with local PEM files:
    cdk deploy AcmCertificateImportStack \\
      -c domain_name=wisnewski.io \\
      -c certificate_path=/path/to/cert.pem \\
      -c private_key_path=/path/to/key.pem \\
      -c certificate_chain_path=/path/to/chain.pem

Usage with Secrets Manager:
    cdk deploy AcmCertificateImportStack \\
      -c domain_name=wisnewski.io \\
      -c certificate_secret_name=homelab/tls/wisnewski.io
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from aws_cdk import (
    CfnOutput,
    SecretValue,
    Stack,
    aws_certificatemanager as acm,
)
from constructs import Construct


@dataclass(frozen=True)
class AcmImportConfig:
    """Configuration for importing a certificate into ACM."""

    domain_name: str
    subject_alternative_names: Sequence[str] = field(default_factory=list)
    certificate_secret_name: str | None = None
    certificate_path: str | None = None
    private_key_path: str | None = None
    certificate_chain_path: str | None = None


def _read_pem_file(path: str, label: str) -> str:
    pem_path = Path(path).expanduser()
    if not pem_path.is_file():
        raise FileNotFoundError(f"{label} not found: {pem_path}")
    return pem_path.read_text()


def _load_certificate_material(config: AcmImportConfig) -> dict[str, str]:
    """Load certificate, private key, and optional chain from secret or files."""
    if config.certificate_secret_name:
        # Secret must exist before synth when using unsafe_unwrap.
        payload = json.loads(
            SecretValue.secrets_manager(config.certificate_secret_name).unsafe_unwrap()
        )
        material = {
            "certificate_body": payload["certificate"],
            "private_key": payload["privateKey"],
        }
        if chain := payload.get("certificateChain"):
            material["certificate_chain"] = chain
        return material

    if not config.certificate_path or not config.private_key_path:
        raise ValueError(
            "Provide either certificate_secret_name or both certificate_path and "
            "private_key_path via stack config / CDK context."
        )

    material = {
        "certificate_body": _read_pem_file(config.certificate_path, "Certificate"),
        "private_key": _read_pem_file(config.private_key_path, "Private key"),
    }
    if config.certificate_chain_path:
        material["certificate_chain"] = _read_pem_file(
            config.certificate_chain_path,
            "Certificate chain",
        )
    return material


class AcmCertificateImportStack(Stack):
    """
    Import an existing X.509 certificate and private key into ACM.

    The imported certificate can be attached to ALB, CloudFront, API Gateway, etc.
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        config: AcmImportConfig,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.config = config
        material = _load_certificate_material(config)

        cert_kwargs: dict = {
            "certificate_body": material["certificate_body"],
            "private_key": material["private_key"],
            "domain_name": config.domain_name,
        }
        if chain := material.get("certificate_chain"):
            cert_kwargs["certificate_chain"] = chain
        if config.subject_alternative_names:
            cert_kwargs["subject_alternative_names"] = list(config.subject_alternative_names)

        self.certificate = acm.CfnCertificate(
            self,
            "ImportedCertificate",
            **cert_kwargs,
        )

        CfnOutput(
            self,
            "CertificateArn",
            value=self.certificate.ref,
            description="ARN of the imported ACM certificate",
            export_name=f"{construct_id}-CertificateArn",
        )

        CfnOutput(
            self,
            "DomainName",
            value=config.domain_name,
            description="Primary domain name on the imported certificate",
        )

        CfnOutput(
            self,
            "RenewalReminder",
            value=(
                "Imported certificates are NOT auto-renewed by ACM. "
                "Re-import a renewed certificate before it expires."
            ),
            description="Operational reminder",
        )


def _config_from_context(app) -> AcmImportConfig:
    domain_name = app.node.try_get_context("domain_name")
    if not domain_name:
        raise ValueError("Set -c domain_name=example.com")

    sans = app.node.try_get_context("subject_alternative_names") or []
    if isinstance(sans, str):
        sans = [s.strip() for s in sans.split(",") if s.strip()]

    return AcmImportConfig(
        domain_name=domain_name,
        subject_alternative_names=sans,
        certificate_secret_name=app.node.try_get_context("certificate_secret_name"),
        certificate_path=app.node.try_get_context("certificate_path"),
        private_key_path=app.node.try_get_context("private_key_path"),
        certificate_chain_path=app.node.try_get_context("certificate_chain_path"),
    )


# ---------------------------------------------------------------------------
# Example CDK app entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from aws_cdk import App

    app = App()

    AcmCertificateImportStack(
        app,
        "AcmCertificateImportStack",
        config=_config_from_context(app),
    )

    app.synth()
