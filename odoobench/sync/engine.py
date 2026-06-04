"""
Sync Engine for Odoo Order Sync

Handles syncing records between Odoo instances using OdooRPC.
"""

import logging
import socket
from typing import Optional, Dict, Any, List, Callable, Set, Tuple
from datetime import datetime

try:
    import odoorpc
except ImportError:
    odoorpc = None

try:
    import paramiko
    from paramiko import SSHClient
except ImportError:
    paramiko = None

from ..db.odoo_connection_manager import OdooInstanceManager
import threading
import os


logger = logging.getLogger(__name__)


class SSHTunnel:
    """Simple SSH tunnel for forwarding a local port to a remote port."""

    def __init__(self, ssh_host: str, ssh_port: int, ssh_user: str,
                 ssh_password: str = None, ssh_key_path: str = None,
                 remote_host: str = 'localhost', remote_port: int = 8069):
        self.ssh_host = ssh_host
        self.ssh_port = ssh_port
        self.ssh_user = ssh_user
        self.ssh_password = ssh_password
        self.ssh_key_path = ssh_key_path
        self.remote_host = remote_host
        self.remote_port = remote_port

        self._ssh_client: Optional[SSHClient] = None
        self._transport = None
        self._local_port: Optional[int] = None
        self._server_socket = None
        self._running = False
        self._thread = None

    def start(self) -> int:
        """Start the SSH tunnel and return the local port."""
        if paramiko is None:
            raise ImportError("paramiko is required for SSH tunneling")

        # Connect SSH
        self._ssh_client = SSHClient()
        self._ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs = {
            'hostname': self.ssh_host,
            'port': self.ssh_port,
            'username': self.ssh_user,
        }

        if self.ssh_key_path and os.path.exists(os.path.expanduser(self.ssh_key_path)):
            connect_kwargs['key_filename'] = os.path.expanduser(self.ssh_key_path)
        elif self.ssh_password:
            connect_kwargs['password'] = self.ssh_password

        self._ssh_client.connect(**connect_kwargs)
        self._transport = self._ssh_client.get_transport()

        # Find a free local port
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(('127.0.0.1', 0))
        self._local_port = self._server_socket.getsockname()[1]
        self._server_socket.listen(1)

        # Start forwarding thread
        self._running = True
        self._thread = threading.Thread(target=self._forward_loop, daemon=True)
        self._thread.start()

        return self._local_port

    def _forward_loop(self):
        """Accept connections and forward through SSH tunnel."""
        while self._running:
            try:
                self._server_socket.settimeout(1.0)
                try:
                    client_socket, addr = self._server_socket.accept()
                except socket.timeout:
                    continue

                # Open channel to remote
                channel = self._transport.open_channel(
                    'direct-tcpip',
                    (self.remote_host, self.remote_port),
                    ('127.0.0.1', 0)
                )

                # Forward in both directions
                threading.Thread(
                    target=self._forward_data,
                    args=(client_socket, channel),
                    daemon=True
                ).start()
                threading.Thread(
                    target=self._forward_data,
                    args=(channel, client_socket),
                    daemon=True
                ).start()

            except Exception as e:
                if self._running:
                    logger.error(f"Tunnel error: {e}")
                break

    def _forward_data(self, src, dst):
        """Forward data from src to dst."""
        try:
            while self._running:
                data = src.recv(4096)
                if not data:
                    break
                dst.sendall(data)
        except Exception:
            pass

    def stop(self):
        """Stop the SSH tunnel."""
        self._running = False
        if self._server_socket:
            try:
                self._server_socket.close()
            except Exception:
                pass
        if self._ssh_client:
            try:
                self._ssh_client.close()
            except Exception:
                pass

    @property
    def local_port(self) -> Optional[int]:
        return self._local_port


# Fields to exclude when syncing (computed fields, internal fields, etc.)
EXCLUDED_FIELDS = {
    'id', 'create_uid', 'create_date', 'write_uid', 'write_date',
    '__last_update', 'display_name', 'message_ids', 'message_follower_ids',
    'message_partner_ids', 'message_channel_ids', 'message_attachment_count',
    'message_has_error', 'message_has_error_counter', 'message_has_sms_error',
    'message_needaction', 'message_needaction_counter', 'message_unread',
    'message_unread_counter', 'message_main_attachment_id', 'website_message_ids',
    'activity_ids', 'activity_state', 'activity_user_id', 'activity_type_id',
    'activity_type_icon', 'activity_date_deadline', 'activity_summary',
    'activity_exception_decoration', 'activity_exception_icon',
}

# Explicit field lists for models we sync - safer than auto-detecting
# These are the core fields needed for sale orders
SYNC_FIELDS = {
    'sale.order': [
        'name', 'state', 'date_order', 'partner_id', 'partner_invoice_id',
        'partner_shipping_id', 'pricelist_id', 'currency_id', 'user_id',
        'team_id', 'company_id', 'warehouse_id', 'commitment_date',
        'client_order_ref', 'origin', 'note', 'fiscal_position_id',
        'payment_term_id', 'validity_date', 'amount_untaxed', 'amount_tax',
        'amount_total',
    ],
    'sale.order.line': [
        'order_id', 'sequence', 'name', 'product_id', 'product_uom_qty',
        'product_uom', 'price_unit', 'discount', 'tax_id', 'price_subtotal',
        'price_total', 'state', 'company_id', 'currency_id',
    ],
}


class SyncEngine:
    """
    Engine for syncing Odoo records between instances.

    Uses OdooRPC to read from source and write to target.
    Maintains ID mapping in sync_transactions table.
    """

    def __init__(
        self,
        instance_manager: OdooInstanceManager = None,
        progress_callback: Callable[[int, str], None] = None,
        log_callback: Callable[[str, str], None] = None,
    ):
        """
        Initialize the sync engine.

        Args:
            instance_manager: Connection manager for instances
            progress_callback: Callback for progress updates (percent, message)
            log_callback: Callback for log messages (message, level)
        """
        if odoorpc is None:
            raise ImportError("odoorpc is required for sync. Install with: pip install odoorpc")

        self.instance_manager = instance_manager or OdooInstanceManager()
        self.progress_callback = progress_callback
        self.log_callback = log_callback

        self._source_odoo: Optional[odoorpc.ODOO] = None
        self._target_odoo: Optional[odoorpc.ODOO] = None
        self._source_instance: Optional[Dict[str, Any]] = None
        self._target_instance: Optional[Dict[str, Any]] = None

        self._stop_requested = False

    def _log(self, message: str, level: str = "info"):
        """Log a message."""
        logger.log(getattr(logging, level.upper(), logging.INFO), message)
        if self.log_callback:
            self.log_callback(message, level)

    def _progress(self, percent: int, message: str):
        """Report progress."""
        if self.progress_callback:
            self.progress_callback(percent, message)

    def stop(self):
        """Request sync to stop."""
        self._stop_requested = True

    def connect(
        self,
        source_instance_id: int,
        target_instance_id: int,
    ) -> bool:
        """
        Connect to source and target Odoo instances.

        Args:
            source_instance_id: ID of source instance (production)
            target_instance_id: ID of target instance (replica)

        Returns:
            True if both connections successful
        """
        self._source_instance = self.instance_manager.get_instance(source_instance_id)
        self._target_instance = self.instance_manager.get_instance(target_instance_id)

        if not self._source_instance:
            self._log(f"Source instance {source_instance_id} not found", "error")
            return False

        if not self._target_instance:
            self._log(f"Target instance {target_instance_id} not found", "error")
            return False

        # Check allow_sync on target
        if not self._target_instance.get('allow_sync'):
            self._log(
                f"Target instance '{self._target_instance['name']}' does not allow sync operations. "
                "Enable 'Allow Sync' in connection settings.",
                "error"
            )
            return False

        # Connect to source
        try:
            self._log(f"Connecting to source: {self._source_instance['name']}")
            self._source_odoo = self._connect_odoorpc(self._source_instance)
            self._log(f"Connected to source: {self._source_instance['db_name']}", "success")
        except Exception as e:
            self._log(f"Failed to connect to source: {e}", "error")
            return False

        # Connect to target
        try:
            self._log(f"Connecting to target: {self._target_instance['name']}")
            self._target_odoo = self._connect_odoorpc(self._target_instance)
            self._log(f"Connected to target: {self._target_instance['db_name']}", "success")
        except Exception as e:
            self._log(f"Failed to connect to target: {e}", "error")
            return False

        return True

    def _connect_odoorpc(self, instance: Dict[str, Any]) -> odoorpc.ODOO:
        """
        Create an OdooRPC connection to an instance.

        Args:
            instance: Instance configuration dict

        Returns:
            Connected OdooRPC instance
        """
        # Derive Odoo HTTP host from connection settings:
        # 1. If SSH configured, use SSH host (Odoo usually runs on same server)
        # 2. Otherwise use localhost
        if instance.get('host') and instance.get('host') != 'localhost':
            host = instance.get('host')
        else:
            host = 'localhost'

        # Odoo HTTP port is always 8069 unless specified
        port = instance.get('odoo_http_port', 8069)

        odoo = odoorpc.ODOO(host, port=port)

        # Login using Odoo web credentials
        db_name = instance.get('db_name')
        odoo_user = instance.get('odoo_user') or 'admin'
        odoo_password = instance.get('odoo_password') or ''

        odoo.login(db_name, odoo_user, odoo_password)

        return odoo

    def disconnect(self):
        """Disconnect from both instances."""
        # OdooRPC doesn't have an explicit disconnect method
        self._source_odoo = None
        self._target_odoo = None

    def sync_model(
        self,
        model: str,
        domain: List = None,
        fields: List[str] = None,
        batch_size: int = 100,
        parent_mapping: Dict[str, Dict[int, int]] = None,
        sync_from_date: str = None,
    ) -> Dict[str, Any]:
        """
        Sync a model from source to target.

        Args:
            model: Model name (e.g., 'sale.order')
            domain: Optional domain filter
            fields: Specific fields to sync (None for all)
            batch_size: Number of records per batch
            parent_mapping: Mapping of parent model IDs (model -> {source_id: target_id})
            sync_from_date: Only sync records with write_date >= this date (YYYY-MM-DD HH:MM:SS)
                           Use this when target was seeded from a backup to skip existing records.

        Returns:
            Dict with sync results: {'created': int, 'updated': int, 'errors': int}
        """
        if not self._source_odoo or not self._target_odoo:
            raise RuntimeError("Not connected. Call connect() first.")

        self._stop_requested = False
        results = {'created': 0, 'updated': 0, 'errors': 0, 'skipped': 0}

        source_id = self._source_instance['id']
        target_id = self._target_instance['id']

        # Determine the cutoff date for incremental sync
        last_sync = self.instance_manager.get_last_sync_time(model, source_id, target_id)

        # Use sync_from_date if provided (for initial sync after backup restore)
        # Otherwise use last_sync time for incremental sync
        cutoff_date = sync_from_date or last_sync

        # Build domain
        search_domain = domain or []
        if cutoff_date:
            search_domain = search_domain + [('write_date', '>', cutoff_date)]

        self._log(f"Syncing {model}...")
        if cutoff_date:
            self._log(f"  Only records modified after: {cutoff_date}")

        # Get source records
        try:
            source_model = self._source_odoo.env[model]
            record_ids = source_model.search(search_domain)
        except Exception as e:
            self._log(f"Error searching {model}: {e}", "error")
            return results

        total = len(record_ids)
        self._log(f"  Found {total} records to sync")

        if total == 0:
            return results

        # Get fields to sync - prefer explicit list, fall back to auto-detect
        if not fields:
            if model in SYNC_FIELDS:
                fields = SYNC_FIELDS[model]
                self._log(f"  Using explicit field list ({len(fields)} fields)")
            else:
                fields = self._get_syncable_fields(model)
                self._log(f"  Auto-detected {len(fields)} fields")

        # Process in batches
        for i in range(0, total, batch_size):
            if self._stop_requested:
                self._log("Sync stopped by user", "warning")
                break

            batch_ids = record_ids[i:i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size

            self._progress(
                int((i / total) * 100),
                f"Syncing {model} batch {batch_num}/{total_batches}"
            )

            try:
                # Read source records
                records = source_model.read(batch_ids, fields + ['write_date'])

                for record in records:
                    try:
                        result = self._sync_record(
                            model, record, fields, parent_mapping
                        )
                        if result == 'created':
                            results['created'] += 1
                        elif result == 'updated':
                            results['updated'] += 1
                        elif result == 'skipped':
                            results['skipped'] += 1
                    except Exception as e:
                        self._log(f"Error syncing {model} {record['id']}: {e}", "error")
                        results['errors'] += 1

            except Exception as e:
                self._log(f"Error reading batch from {model}: {e}", "error")
                results['errors'] += batch_size

        self._progress(100, f"Completed {model}")
        self._log(
            f"  Sync complete: {results['created']} created, "
            f"{results['updated']} updated, {results['errors']} errors"
        )

        return results

    def _get_syncable_fields(self, model: str) -> List[str]:
        """Get list of fields that can be synced for a model."""
        try:
            source_model = self._source_odoo.env[model]
            all_fields = source_model.fields_get()

            syncable = []
            for name, info in all_fields.items():
                if name in EXCLUDED_FIELDS:
                    continue

                # Skip computed fields without store
                if info.get('compute') and not info.get('store'):
                    continue

                # Skip related fields that aren't stored
                if info.get('related') and not info.get('store'):
                    continue

                syncable.append(name)

            return syncable

        except Exception as e:
            self._log(f"Error getting fields for {model}: {e}", "warning")
            return []

    def _sync_record(
        self,
        model: str,
        record: Dict[str, Any],
        fields: List[str],
        parent_mapping: Dict[str, Dict[int, int]] = None,
    ) -> str:
        """
        Sync a single record.

        Returns:
            'created', 'updated', or 'skipped'
        """
        source_id = self._source_instance['id']
        target_id = self._target_instance['id']
        record_id = record['id']
        write_date = record.get('write_date', '')

        # Check if already synced
        mapping = self.instance_manager.get_sync_mapping(
            model, source_id, record_id, target_id
        )

        # Prepare values for target
        values = self._prepare_values(model, record, fields, parent_mapping)

        if mapping:
            # Update existing record
            target_record_id = mapping['target_id']

            # Check if record changed since last sync
            if mapping['source_write_date'] == write_date:
                return 'skipped'

            try:
                target_model = self._target_odoo.env[model]
                target_model.write([target_record_id], values)

                # Update mapping
                self.instance_manager.save_sync_mapping(
                    model, source_id, record_id, target_id,
                    target_record_id, write_date
                )

                return 'updated'

            except Exception as e:
                raise RuntimeError(f"Failed to update {model} {target_record_id}: {e}")

        else:
            # Create new record
            try:
                target_model = self._target_odoo.env[model]
                new_id = target_model.create(values)

                # Save mapping
                self.instance_manager.save_sync_mapping(
                    model, source_id, record_id, target_id,
                    new_id, write_date
                )

                return 'created'

            except Exception as e:
                raise RuntimeError(f"Failed to create {model}: {e}")

    def _prepare_values(
        self,
        model: str,
        record: Dict[str, Any],
        fields: List[str],
        parent_mapping: Dict[str, Dict[int, int]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare record values for writing to target.

        Handles ID remapping for relational fields.
        """
        source_id = self._source_instance['id']
        target_id = self._target_instance['id']
        parent_mapping = parent_mapping or {}

        # Get field info for type checking
        source_model = self._source_odoo.env[model]
        field_info = source_model.fields_get(fields)

        values = {}

        for field in fields:
            if field not in record or field in EXCLUDED_FIELDS:
                continue

            value = record[field]
            info = field_info.get(field, {})
            field_type = info.get('type')

            if field_type == 'many2one':
                if value:
                    # value is [id, name] tuple
                    related_id = value[0] if isinstance(value, (list, tuple)) else value
                    comodel = info.get('relation')

                    # Check parent mapping first
                    if comodel in parent_mapping and related_id in parent_mapping[comodel]:
                        values[field] = parent_mapping[comodel][related_id]
                    else:
                        # Check sync mapping
                        mapping = self.instance_manager.get_sync_mapping(
                            comodel, source_id, related_id, target_id
                        )
                        if mapping:
                            values[field] = mapping['target_id']
                        else:
                            # Assume same ID on both instances (master data)
                            values[field] = related_id
                else:
                    values[field] = False

            elif field_type == 'many2many':
                if value:
                    comodel = info.get('relation')
                    remapped_ids = []

                    for related_id in value:
                        if comodel in parent_mapping and related_id in parent_mapping[comodel]:
                            remapped_ids.append(parent_mapping[comodel][related_id])
                        else:
                            mapping = self.instance_manager.get_sync_mapping(
                                comodel, source_id, related_id, target_id
                            )
                            if mapping:
                                remapped_ids.append(mapping['target_id'])
                            else:
                                remapped_ids.append(related_id)

                    values[field] = [(6, 0, remapped_ids)]
                else:
                    values[field] = [(5, 0, 0)]  # Clear all

            elif field_type == 'one2many':
                # Skip one2many fields - sync the child model separately
                continue

            else:
                # Simple field types
                values[field] = value

        return values

    def sync_sales_orders(
        self,
        domain: List = None,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Sync sale.order and sale.order.line from source to target.

        Automatically detects the last synced order by checking the highest
        order number on the target, then only syncs newer orders.

        Args:
            domain: Optional domain filter for sale.order
            batch_size: Number of orders per batch

        Returns:
            Dict with combined sync results
        """
        results = {
            'sale.order': {'created': 0, 'updated': 0, 'errors': 0, 'skipped': 0},
            'sale.order.line': {'created': 0, 'updated': 0, 'errors': 0, 'skipped': 0},
        }

        # Find the last order number on target to determine where to start
        target_model = self._target_odoo.env['sale.order']
        last_orders = target_model.search_read(
            [], ['name'], order='name desc', limit=1
        )

        sync_domain = domain or []
        if last_orders:
            last_order_name = last_orders[0]['name']
            self._log(f"Last order on target: {last_order_name}")
            sync_domain = sync_domain + [('name', '>', last_order_name)]
        else:
            self._log("No orders on target - syncing all")

        # First sync sale.order
        self._log("Starting sale.order sync...")
        so_results = self.sync_model('sale.order', domain=sync_domain, batch_size=batch_size)
        results['sale.order'] = so_results

        if self._stop_requested:
            return results

        # Build mapping for order_id lookups
        so_mapping = self._get_model_mapping('sale.order')

        # Now sync sale.order.line
        # Build domain to get lines for synced orders
        synced_order_ids = list(so_mapping.keys())
        if synced_order_ids:
            line_domain = [('order_id', 'in', synced_order_ids)]
            if domain:
                # Extend with any additional filters
                pass

            self._log("Starting sale.order.line sync...")
            sol_results = self.sync_model(
                'sale.order.line',
                domain=line_domain,
                batch_size=batch_size * 5,  # More lines per batch
                parent_mapping={'sale.order': so_mapping},
            )
            results['sale.order.line'] = sol_results

        return results

    def _get_model_mapping(self, model: str) -> Dict[int, int]:
        """Get source_id -> target_id mapping for a model."""
        source_id = self._source_instance['id']
        target_id = self._target_instance['id']

        # Query all mappings for this model/source/target
        import sqlite3
        conn = sqlite3.connect(self.instance_manager.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT source_id, target_id FROM sync_transactions
            WHERE model = ? AND source_instance_id = ? AND target_instance_id = ?
        """, (model, source_id, target_id))

        mapping = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        return mapping

    def detect_deletes(self, model: str) -> List[int]:
        """
        Detect records that were deleted on source.

        Returns list of source IDs that no longer exist.
        """
        if not self._source_odoo:
            raise RuntimeError("Not connected. Call connect() first.")

        source_id = self._source_instance['id']
        target_id = self._target_instance['id']

        # Get all source IDs we've synced
        synced_ids = self.instance_manager.get_synced_source_ids(
            model, source_id, target_id
        )

        if not synced_ids:
            return []

        # Check which ones still exist on source
        source_model = self._source_odoo.env[model]
        existing_ids = source_model.search([('id', 'in', synced_ids)])

        # Find deleted
        deleted_ids = set(synced_ids) - set(existing_ids)

        return list(deleted_ids)

    def delete_orphans(self, model: str, deleted_source_ids: List[int]) -> int:
        """
        Delete records on target that were deleted on source.

        Args:
            model: Model name
            deleted_source_ids: List of source IDs that were deleted

        Returns:
            Number of records deleted
        """
        if not self._target_odoo:
            raise RuntimeError("Not connected. Call connect() first.")

        source_id = self._source_instance['id']
        target_id = self._target_instance['id']

        deleted_count = 0

        for source_record_id in deleted_source_ids:
            mapping = self.instance_manager.get_sync_mapping(
                model, source_id, source_record_id, target_id
            )

            if mapping:
                try:
                    target_model = self._target_odoo.env[model]
                    target_model.unlink([mapping['target_id']])

                    # Remove mapping
                    self.instance_manager.delete_sync_mapping(
                        model, source_id, source_record_id, target_id
                    )

                    deleted_count += 1
                    self._log(f"Deleted {model} {mapping['target_id']} (source: {source_record_id})")

                except Exception as e:
                    self._log(f"Error deleting {model} {mapping['target_id']}: {e}", "error")

        return deleted_count

    def run_full_sync(
        self,
        include_deletes: bool = True,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Run a full sync of sales orders including delete detection.

        Automatically determines which orders to sync by comparing
        the last order number on target vs source.

        Args:
            include_deletes: Whether to detect and remove deleted records
            batch_size: Batch size for sync operations

        Returns:
            Complete sync results
        """
        results = {
            'sync': {},
            'deletes': {},
            'errors': [],
        }

        try:
            # Sync orders and lines
            sync_results = self.sync_sales_orders(batch_size=batch_size)
            results['sync'] = sync_results

            if self._stop_requested:
                return results

            # Handle deletes
            if include_deletes:
                self._log("Checking for deleted records...")

                for model in ['sale.order.line', 'sale.order']:  # Lines first
                    deleted = self.detect_deletes(model)
                    if deleted:
                        self._log(f"Found {len(deleted)} deleted {model} records")
                        count = self.delete_orphans(model, deleted)
                        results['deletes'][model] = count
                    else:
                        results['deletes'][model] = 0

            self._log("Full sync complete", "success")

        except Exception as e:
            self._log(f"Sync error: {e}", "error")
            results['errors'].append(str(e))

        return results
