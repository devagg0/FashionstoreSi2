import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { CategoryCard } from '../../shared/components/category-card/category-card';
import { Icon, IconName } from '../../shared/components/icon/icon';
import { SectionCard } from '../../shared/components/section-card/section-card';

interface StyleCollection {
  title: string;
  image: string;
  alt: string;
  position?: string;
}

interface Benefit {
  icon: IconName;
  title: string;
  description: string;
}

@Component({
  selector: 'app-home',
  imports: [CategoryCard, Icon, RouterLink, SectionCard],
  templateUrl: './home.html',
  styleUrl: './home.scss',
})
export class Home {
  protected readonly heroImage =
    'https://images.unsplash.com/photo-1483985988355-763728e1935b?auto=format&fit=crop&w=1800&q=85';

  protected readonly collections: readonly StyleCollection[] = [
    {
      title: 'HOMBRE',
      image:
        'https://images.unsplash.com/photo-1487222477894-8943e31ef7b2?auto=format&fit=crop&w=1000&q=82',
      alt: 'Modelo con estilo masculino contemporáneo',
      position: 'center top',
    },
    {
      title: 'MUJER',
      image:
        'https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=1000&q=82',
      alt: 'Modelo con estilo femenino contemporáneo',
      position: 'center top',
    },
    {
      title: 'UNISEX',
      image:
        'https://images.unsplash.com/photo-1523381210434-271e8be1f52b?auto=format&fit=crop&w=1000&q=82',
      alt: 'Selección de prendas de estilo unisex',
    },
  ];

  protected readonly categories = [
    'Poleras',
    'Camisas',
    'Pantalones',
    'Shorts',
    'Chaquetas',
    'Vestidos',
  ] as const;

  protected readonly benefits: readonly Benefit[] = [
    {
      icon: 'map-pin',
      title: 'Disponibilidad por sucursal',
      description: 'Encuentra dónde está lo que buscas.',
    },
    {
      icon: 'store',
      title: 'Reserva tus prendas',
      description: 'Separa tus prendas para verlas en tienda.',
    },
    {
      icon: 'monitor-smartphone',
      title: 'Compra desde web y móvil',
      description: 'Tu experiencia FashionStore, donde estés.',
    },
  ];
}
