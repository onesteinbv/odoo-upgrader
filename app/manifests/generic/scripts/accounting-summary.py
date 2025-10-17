
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
    per_account = env["account.move.line"].read_group([], ["debit", "credit"], ["account_id"])
    per_partner = env["account.move.line"].read_group([], ["debit", "credit"], ["partner_id"])
    per_journal = env["account.move.line"].read_group([], ["debit", "credit"], ["journal_id"])
    per_matching_number = env["account.move.line"].read_group([], ["debit", "credit"], ["matching_number"])
    analytic_lines = env["account.analytic.line"].read_group([], ["amount"], ["account_id"])
    
    def _to_summary(line, group_field, fields):
        return {**{
            "id": line[group_field] and line[group_field][0] or False,
            "count": line["%s_count" % group_field],
        }, **{
            field: line[field] for field in fields
        }}
    
    data = {
        "per_account": [_to_summary(line, "account_id", ["debit", "credit"]) for line in per_account],
        "per_partner": [_to_summary(line, "partner_id", ["debit", "credit"]) for line in per_partner],
        "per_journal": [_to_summary(line, "journal_id", ["debit", "credit"]) for line in per_journal],
        "per_matching_number": [_to_summary(line, "matching_number", ["debit", "credit"]) for line in per_matching_number],
        "analytic_lines": [_to_summary(line, "account_id", ["amount"]) for line in analytic_lines]
    }

    hexdigest = sha256(json.dumps(data).encode()).hexdigest()

    if digest:
        click.echo(hexdigest)
    else:
        data.update(digest=hexdigest)
        click.echo(json.dumps(data))

if __name__ == "__main__":
    main()
