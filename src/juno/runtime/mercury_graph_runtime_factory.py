"""Build a Mercury :class:`~mercury.graph.runtime.GraphRuntime` without FastAPI ``Request``.

Mirrors ``mercury.service.dependencies.get_graph_runtime`` wiring using
:class:`~mercury.config.MercurySettings` from :func:`~mercury.config.get_settings`
so Juno local mode does not need an ASGI app. Tests may monkeypatch
:func:`build_mercury_graph_runtime_for_local`.
"""

from __future__ import annotations

from mercury.config import MercurySettings, get_settings
from mercury.custody import MercuryWalletSigner
from mercury.graph.nodes_erc20 import ERC20GraphDependencies
from mercury.graph.nodes_native import NativeGraphDependencies
from mercury.graph.nodes_swaps import SwapGraphDependencies
from mercury.graph.nodes_transaction import TransactionGraphDependencies
from mercury.graph.runtime import GraphRuntime, build_default_runtime
from mercury.policy.idempotency import InMemoryIdempotencyStore
from mercury.policy.risk import TransactionPolicyEngine
from mercury.providers import Web3EnsAddressResolver, Web3ProviderFactory
from mercury.service.dependencies import get_secret_store, get_swap_router
from mercury.tools.registry import ReadOnlyToolRegistry
from mercury.tools.portfolio_tokens import AlchemyPortfolioToolDeps
from mercury.tools.token_prices import AlchemyPricesToolDeps
from mercury.tools.transfer_history import AlchemyTransfersToolDeps
from mercury.tools.transactions import RequestMetadataTransactionApprover, Web3TransactionBackend


def build_mercury_graph_runtime_for_local(settings: MercurySettings | None = None) -> GraphRuntime:
    """Construct the default Mercury graph runtime (same deps as FastAPI ``get_graph_runtime``)."""
    resolved = settings if settings is not None else get_settings()
    secret_store = get_secret_store(resolved)
    provider_factory = Web3ProviderFactory(secret_store)
    signer = MercuryWalletSigner(secret_store)
    ens_resolver = Web3EnsAddressResolver(provider_factory)
    swap_router = get_swap_router(resolved, secret_store)
    transaction_deps = TransactionGraphDependencies(
        backend=Web3TransactionBackend(provider_factory),
        signer=signer,
        policy_engine=TransactionPolicyEngine(),
        approver=RequestMetadataTransactionApprover(),
        idempotency_store=InMemoryIdempotencyStore(),
    )
    alchemy_prices: AlchemyPricesToolDeps | None = None
    alchemy_portfolio: AlchemyPortfolioToolDeps | None = None
    alchemy_transfers: AlchemyTransfersToolDeps | None = None
    alchemy_path = resolved.alchemy_api_secret_path.strip()
    if alchemy_path:
        alchemy_prices = AlchemyPricesToolDeps(
            secret_store=secret_store,
            api_key_secret_path=alchemy_path,
        )
        alchemy_portfolio = AlchemyPortfolioToolDeps(
            secret_store=secret_store,
            api_key_secret_path=alchemy_path,
        )
        alchemy_transfers = AlchemyTransfersToolDeps(
            secret_store=secret_store,
            api_key_secret_path=alchemy_path,
        )

    return build_default_runtime(
        registry=ReadOnlyToolRegistry.from_provider_factory(
            provider_factory,
            alchemy_prices=alchemy_prices,
            alchemy_portfolio=alchemy_portfolio,
            alchemy_transfers=alchemy_transfers,
        ),
        erc20_deps=ERC20GraphDependencies(
            provider_factory=provider_factory,
            address_resolver=signer,
        ),
        native_deps=NativeGraphDependencies(address_resolver=signer),
        swap_deps=SwapGraphDependencies(
            router=swap_router,
            provider_factory=provider_factory,
            address_resolver=signer,
        ),
        transaction_deps=transaction_deps,
        runtime_settings=resolved,
        ens_resolver=ens_resolver,
    )


__all__ = ["build_mercury_graph_runtime_for_local"]
