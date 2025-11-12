
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="odoo")


from hashlib import sha256
import json
import click
import click_odoo


@click.command()
@click.option("--digest", is_flag=True, help="Output only the digest of the summary")
@click_odoo.env_options(default_log_level="critical")
def main(env, digest):
    """ Outputs a summary of accounting data in the Odoo database.
    The summary includes totals per account, partner, journal, matching number,
    and analytic account. The output is in JSON format, with an additional SHA256
    digest of the summary data for fast integrity verification. """
    installed_modules = env["ir.module.module"].search([("state", "=", "installed"), ("name", "=", "account")])
    if not installed_modules:
        click.echo("Module 'account' is not installed, exiting...")
        return

    move_line_sudo = env["account.move.line"].sudo()
    analytic_line_sudo = env["account.analytic.line"].sudo()
    per_account = move_line_sudo.read_group([], ["debit", "credit"], ["account_id"])
    per_partner = move_line_sudo.read_group([], ["debit", "credit"], ["partner_id"])
    per_journal = move_line_sudo.read_group([], ["debit", "credit"], ["journal_id"])
    per_matching_number = move_line_sudo.read_group([], ["debit", "credit"], ["matching_number"], orderby="matching_number")
    per_date = move_line_sudo.read_group([], ["debit", "credit"], ["date:month"], orderby="date")
    analytic_lines = analytic_line_sudo.read_group([], ["amount"], ["account_id"])
    
    def _to_summary(line, group_field, fields):
        count_key = "%s_count" % group_field if ":" not in group_field else group_field.split(":")[0] + "_count"
        summary_id = False
        if line[group_field]:
            if isinstance(line[group_field], tuple):
                summary_id = line[group_field][0]
            else:
                summary_id = line[group_field]
        return {**{
            "id": summary_id,
            "count": line[count_key],
        }, **{
            field: line[field] for field in fields
        }}
    
    def _order_by_id(lines):
        return list(sorted(lines, key=lambda l: l["id"]))
        
    data = {
        "per_account": _order_by_id([_to_summary(line, "account_id", ["debit", "credit"]) for line in per_account]),
        "per_partner": _order_by_id([_to_summary(line, "partner_id", ["debit", "credit"]) for line in per_partner]),
        "per_journal": _order_by_id([_to_summary(line, "journal_id", ["debit", "credit"]) for line in per_journal]),
        "per_matching_number": [_to_summary(line, "matching_number", ["debit", "credit"]) for line in per_matching_number],
        "per_date": [_to_summary(line, "date:month", ["debit", "credit"]) for line in per_date],
        # NB: analytic accounting has been changed alot in > 17, so we disable this check for now 
        # "analytic_lines": _order_by_id([_to_summary(line, "account_id", ["amount"]) for line in analytic_lines])
    }

    hexdigest = sha256(json.dumps(data).encode()).hexdigest()

    if digest:
        click.echo(hexdigest)
    else:
        data.update(digest=hexdigest)
        click.echo(json.dumps(data))

if __name__ == "__main__":
    main()
