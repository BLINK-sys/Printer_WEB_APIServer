import csv
import io
from datetime import datetime, timezone

import requests
from flask import Blueprint, Response, jsonify, request

from ..extensions import db
from ..middleware.auth_required import jwt_required_custom
from ..models.cloud_product import CloudProduct
from ..models.product_database import ProductDatabase

products_bp = Blueprint('products', __name__)


def _check_db_ownership(user, db_id):
    """Get a database and verify the user owns it."""
    pdb = ProductDatabase.query.get(db_id)
    if not pdb:
        return None, (jsonify({'error': 'Database not found'}), 404)
    if pdb.user_id != user.id:
        return None, (jsonify({'error': 'Access denied'}), 403)
    return pdb, None


# --- Databases ---

@products_bp.route('/databases', methods=['GET'])
@jwt_required_custom
def list_databases(user):
    databases = ProductDatabase.query.filter_by(user_id=user.id).order_by(
        ProductDatabase.updated_at.desc()
    ).all()
    return jsonify([d.to_dict() for d in databases]), 200


@products_bp.route('/databases', methods=['POST'])
@jwt_required_custom
def create_database(user):
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    name = data.get('name', '').strip()
    if not name:
        return jsonify({'error': 'Database name is required'}), 400

    pdb = ProductDatabase(
        user_id=user.id,
        name=name,
        description=data.get('description', '').strip() or None,
    )
    db.session.add(pdb)
    db.session.commit()
    return jsonify(pdb.to_dict()), 201


@products_bp.route('/databases/<int:db_id>', methods=['PUT'])
@jwt_required_custom
def update_database(user, db_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    name = data.get('name', '').strip()
    if name:
        pdb.name = name
    if 'description' in data:
        pdb.description = data['description'].strip() or None

    db.session.commit()
    return jsonify(pdb.to_dict()), 200


@products_bp.route('/databases/<int:db_id>', methods=['DELETE'])
@jwt_required_custom
def delete_database(user, db_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    db.session.delete(pdb)
    db.session.commit()
    return jsonify({'message': 'Database deleted'}), 200


# --- Products within a database ---

@products_bp.route('/databases/<int:db_id>/products', methods=['GET'])
@jwt_required_custom
def list_products(user, db_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    search = request.args.get('search', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 50, type=int)
    per_page = min(per_page, 200)

    query = CloudProduct.query.filter_by(database_id=db_id)

    if search:
        like_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                CloudProduct.name_kz.ilike(like_pattern),
                CloudProduct.name_full.ilike(like_pattern),
                CloudProduct.barcode.ilike(like_pattern),
            )
        )

    query = query.order_by(CloudProduct.name_kz)
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        'products': [p.to_dict() for p in pagination.items],
        'total': pagination.total,
        'page': pagination.page,
        'pages': pagination.pages,
        'per_page': per_page,
    }), 200


@products_bp.route('/databases/<int:db_id>/products', methods=['POST'])
@jwt_required_custom
def add_products(user, db_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    # Support single product or array
    products_data = data if isinstance(data, list) else [data]
    created = []

    for item in products_data:
        name_kz = item.get('name_kz', '').strip()
        name_full = item.get('name_full', '').strip()
        barcode = item.get('barcode', '').strip()
        price = item.get('price', 0)

        if not barcode:
            continue

        product = CloudProduct(
            database_id=db_id,
            name_kz=name_kz or '',
            name_full=name_full or '',
            barcode=barcode,
            price=price,
        )
        db.session.add(product)
        created.append(product)

    db.session.commit()
    return jsonify({
        'message': f'{len(created)} product(s) added',
        'products': [p.to_dict() for p in created],
    }), 201


@products_bp.route('/databases/<int:db_id>/products/<int:product_id>', methods=['PUT'])
@jwt_required_custom
def update_product(user, db_id, product_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    product = CloudProduct.query.filter_by(id=product_id, database_id=db_id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    if 'name_kz' in data:
        product.name_kz = data['name_kz'].strip()
    if 'name_full' in data:
        product.name_full = data['name_full'].strip()
    if 'barcode' in data:
        product.barcode = data['barcode'].strip()
    if 'price' in data:
        product.price = data['price']

    db.session.commit()
    return jsonify(product.to_dict()), 200


@products_bp.route('/databases/<int:db_id>/products/<int:product_id>', methods=['DELETE'])
@jwt_required_custom
def delete_product(user, db_id, product_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    product = CloudProduct.query.filter_by(id=product_id, database_id=db_id).first()
    if not product:
        return jsonify({'error': 'Product not found'}), 404

    db.session.delete(product)
    db.session.commit()
    return jsonify({'message': 'Product deleted'}), 200


# --- CSV Import/Export ---

@products_bp.route('/databases/<int:db_id>/import-csv', methods=['POST'])
@jwt_required_custom
def import_csv(user, db_id):
    """Import products from CSV URL or raw CSV data."""
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    data = request.get_json()
    if not data:
        return jsonify({'error': 'Request body required'}), 400

    csv_url = data.get('csv_url', '').strip()
    csv_data = data.get('csv_data', '').strip()
    replace_all = data.get('replace_all', False)

    if not csv_url and not csv_data:
        return jsonify({'error': 'csv_url or csv_data is required'}), 400

    try:
        if csv_url:
            resp = requests.get(csv_url, timeout=30)
            resp.raise_for_status()
            raw = resp.content.decode('utf-8-sig')
        else:
            raw = csv_data

        # Auto-detect delimiter
        first_line = raw.split('\n')[0] if raw else ''
        delimiter = ';' if ';' in first_line else ','

        reader = csv.reader(io.StringIO(raw), delimiter=delimiter)
        rows = list(reader)

        if len(rows) < 2:
            return jsonify({'error': 'CSV must have header + at least one data row'}), 400

        # Skip header
        products = []
        for row in rows[1:]:
            if len(row) < 5:
                continue

            barcode = row[3].strip()
            # Handle scientific notation (e.g., 2.022E+12)
            if barcode and ('e' in barcode.lower() or 'E' in barcode):
                try:
                    barcode = str(int(float(barcode)))
                except (ValueError, OverflowError):
                    pass

            if not barcode:
                continue

            try:
                price = float(row[4].strip().replace(',', '.'))
            except (ValueError, IndexError):
                price = 0.0

            products.append(CloudProduct(
                database_id=db_id,
                name_full=row[1].strip() if len(row) > 1 else '',
                name_kz=row[2].strip() if len(row) > 2 else '',
                barcode=barcode,
                price=price,
            ))

        if replace_all:
            CloudProduct.query.filter_by(database_id=db_id).delete()

        for p in products:
            db.session.add(p)

        db.session.commit()

        return jsonify({
            'message': f'{len(products)} products imported',
            'total': len(products),
        }), 200

    except requests.RequestException as e:
        return jsonify({'error': f'Failed to fetch CSV: {str(e)}'}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Import failed: {str(e)}'}), 500


@products_bp.route('/databases/<int:db_id>/export-csv', methods=['GET'])
@jwt_required_custom
def export_csv(user, db_id):
    pdb, error = _check_db_ownership(user, db_id)
    if error:
        return error

    products = CloudProduct.query.filter_by(database_id=db_id).order_by(CloudProduct.name_kz).all()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['#', 'Name', 'NameKZ', 'Barcode', 'Price'])
    for i, p in enumerate(products, 1):
        writer.writerow([i, p.name_full, p.name_kz, p.barcode, float(p.price)])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename={pdb.name}.csv'},
    )
