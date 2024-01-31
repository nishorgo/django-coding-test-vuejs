from django.views import generic
from django.shortcuts import render, redirect
from django.core.paginator import Paginator, PageNotAnInteger, EmptyPage

from operator import itemgetter
from itertools import groupby

from product.models import Variant, Product, ProductVariant
from product.serializers import ProductSerializer, VariantSerializer, ProductVariantSerializer, ProductVariantPriceSerializer, ProductImageSerializer
from rest_framework.generics import get_object_or_404, UpdateAPIView


class CreateProductView(generic.TemplateView):
    template_name = 'products/create.html'

    def get_context_data(self, **kwargs):
        context = super(CreateProductView, self).get_context_data(**kwargs)
        variants = Variant.objects.filter(active=True).values('id', 'title')
        context['product'] = True
        context['variants'] = list(variants.all())
        return context



class ProductListView(generic.ListView):
    model = Product
    template_name = 'products/list.html'
    context_object_name = 'products'
    paginate_by = 5

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        grouped_variants = {}

        # Group ProductVariants by Variant
        product_variants = ProductVariant.objects.select_related('variant').all()
        key_function = itemgetter('variant__id')
        product_variants = sorted(product_variants, key=key_function)
        for variant_id, variants_group in groupby(product_variants, key=key_function):
            grouped_variants[variant_id] = list(variants_group)

        context['grouped_variants'] = grouped_variants

        # Retrieve filter parameters from the request
        title_filter = self.request.GET.get('title', '')
        variant_filter = self.request.GET.get('variant', '')
        price_from = self.request.GET.get('price_from', 0)
        price_to = self.request.GET.get('price_to', float('inf'))
        created_date_filter = self.request.GET.get('date', '')

        # Apply filters to the queryset
        product_list = Product.objects.filter(
            title__icontains=title_filter,
            productvariantprice__variant__title__icontains=variant_filter,
            productvariantprice__price__gte=price_from,
            productvariantprice__price__lte=price_to,
            created_at__date=created_date_filter
        ).distinct()

        # Pagination
        paginator = Paginator(product_list, self.paginate_by)
        page = self.request.GET.get('page')

        try:
            products = paginator.page(page)
        except PageNotAnInteger:
            products = paginator.page(1)
        except EmptyPage:
            products = paginator.page(paginator.num_pages)

        # Counting the product indexes in the current page
        product_start_index = (int(page) - 1) * self.paginate_by + 1 if len(products) > 0 else 0
        product_end_index = product_start_index + len(products) - 1

        context['start_index'] = product_start_index
        context['end_index'] = product_end_index
        context['total_products'] = paginator.count
        context['paginator'] = paginator

        context['title_filter'] = title_filter
        context['variant_filter'] = variant_filter
        context['price_from'] = price_from
        context['price_to'] = price_to
        context['created_date_filter'] = created_date_filter

        return context

    def post(self, request, *args, **kwargs):
        selected_variant_ids = []

        # Retrieve selected variant IDs from the form
        for variant_id, variant_value in request.POST.items():
            if variant_id.startswith('variant_group_') and variant_value:
                selected_variant_ids.append(int(variant_value))

        # Use selected_variant_ids to filter products
        if selected_variant_ids:
            product_list = Product.objects.filter(
                productvariant__variant__id__in=selected_variant_ids
            ).distinct()

            # Pagination
            paginator = Paginator(product_list, self.paginate_by)
            page = request.GET.get('page', 1)

            try:
                products = paginator.page(page)
            except PageNotAnInteger:
                products = paginator.page(1)
            except EmptyPage:
                products = paginator.page(paginator.num_pages)

            # Counting the product indexes in the current page
            product_start_index = (int(page) - 1) * self.paginate_by + 1 if len(products) > 0 else 0
            product_end_index = product_start_index + len(products) - 1

            context = {
                'start_index': product_start_index,
                'end_index': product_end_index,
                'products': products,
                'total_products': paginator.count,
                'paginator': paginator,
                'grouped_variants': {},  # Clear grouped_variants for post requests
            }

            return render(request, self.template_name, context)

        return redirect('list.product')
    


class ProductCreateUpdateAPIView(UpdateAPIView):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer

    def get_object(self):
        return get_object_or_404(Product, pk=self.kwargs['pk'])

    def perform_update(self, serializer):
        instance = serializer.save()

        # Update associated objects
        variant_data = {
            'variant_title': self.request.data.get('variant_title'),
            'variant': {
                'title': self.request.data.get('variant_title'),
                'description': self.request.data.get('variant_description'),
                'active': True 
            },
            'product': instance.id
        }

        variant_instance = instance.productvariant
        if variant_instance:
            variant_serializer = ProductVariantSerializer(variant_instance, data=variant_data, partial=True)
            if variant_serializer.is_valid():
                variant_serializer.save()
        else:
            variant_serializer = ProductVariantSerializer(data=variant_data)
            if variant_serializer.is_valid():
                variant_instance = variant_serializer.save()

        # Update ProductVariantPrice
        price_instance = variant_instance.productvariantprice
        price_data = {
            'product_variant': variant_instance.id,
            'price': self.request.data.get('price'),
            'stock': self.request.data.get('stock')
        }

        if price_instance:
            price_serializer = ProductVariantPriceSerializer(price_instance, data=price_data, partial=True)
            if price_serializer.is_valid():
                price_serializer.save()
        else:
            price_serializer = ProductVariantPriceSerializer(data=price_data)
            if price_serializer.is_valid():
                price_serializer.save()

        # Update ProductImage
        image_instance = instance.productimage
        image_data = {
            'product': instance.id,
            'file_path': self.request.data.get('image_file_path'),
            'thumbnail': self.request.data.get('thumbnail')
        }

        if image_instance:
            image_serializer = ProductImageSerializer(image_instance, data=image_data, partial=True)
            if image_serializer.is_valid():
                image_serializer.save()
        else:
            image_serializer = ProductImageSerializer(data=image_data)
            if image_serializer.is_valid():
                image_serializer.save()