"""
Pure mathematical core for Elliptical NACA Propeller Generator.

This module intentionally has no Autodesk Fusion imports. It is the closest
Python representation of the equations in the upstream OpenSCAD propblade()
implementation and can be imported by ordinary CPython test scripts.

Units and coordinate responsibilities
-------------------------------------

* Every length is expressed in millimetres.
* Angles exposed by this module are expressed in degrees.
* SectionGeometry contains a dimensional planar airfoil.
* WrappedSectionGeometry contains the same airfoil after geometric pitch,
  cylindrical wrapping and azimuthal sweep have been applied.
* Fusion centimetre conversion belongs only in the API adapter module.

Mapping to the upstream SCAD
----------------------------

BladeConfig fields correspond to the user-facing SCAD variables. Key mappings:

    Propeller_Diameter      -> propdia
    Hub_Diameter            -> hubdia
    Blade_Pitch             -> bladepitch
    Max_Chord_Fraction      -> maxchordfrac
    Root_Length             -> propblade() hublen
    Elen_Fraction           -> elenfrac
    Prop_Direction          -> dir
    Centerline              -> centerline
    Sweep_Angle             -> angle_sweep
    Trailing_Edge_Thickness -> te_thickness
    Fairing_Size            -> fairing
    Transition_Point        -> root_transition

The mathematical pipeline is:

    radius
    -> local pitch angle
    -> ellipse-constrained chord
    -> root/mid/tip NACA interpolation
    -> root fairing thickness addition
    -> modified finite trailing edge
    -> pitch rotation
    -> cylindrical wrapping
    -> sweep rotation

Verified invariants
-------------------

* Every wrapped point remains on its requested cylindrical radius to floating
  point precision.
* Root, transition and tip sections are inserted exactly in automatic section
  distributions.
* A negative Blade_Pitch uses the blade length, matching the SCAD behavior.
* The Fusion sweep sign conversion was fixed and confirmed by solid overlay.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping, Sequence


@dataclass(frozen=True)
class BladeConfig:
    propeller_diameter_mm: float
    hub_diameter_mm: float
    blade_pitch_mm: float
    max_chord_fraction: float
    root_length_mm: float
    ellipse_length_fraction: float
    direction: int
    centerline: float
    sweep_angle_deg_per_mm: float
    trailing_edge_thickness_mm: float
    fairing_size_mm: float
    root_naca: str
    mid_naca: str
    tip_naca: str
    transition_point: float
    profile_points: int

    @property
    def root_radius_mm(self) -> float:
        return self.hub_diameter_mm / 2.0

    @property
    def tip_radius_mm(self) -> float:
        return self.propeller_diameter_mm / 2.0

    @property
    def blade_length_mm(self) -> float:
        return self.tip_radius_mm - self.root_radius_mm

    @property
    def effective_pitch_mm(self) -> float:
        return self.blade_pitch_mm if self.blade_pitch_mm >= 0.0 else self.blade_length_mm

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "BladeConfig":
        cfg = cls(
            propeller_diameter_mm=float(values["Propeller_Diameter"]),
            hub_diameter_mm=float(values["Hub_Diameter"]),
            blade_pitch_mm=float(values["Blade_Pitch"]),
            max_chord_fraction=float(values["Max_Chord_Fraction"]),
            root_length_mm=float(values["Root_Length"]),
            ellipse_length_fraction=float(values["Elen_Fraction"]),
            direction=int(values["Prop_Direction"]),
            centerline=float(values["Centerline"]),
            sweep_angle_deg_per_mm=float(values["Sweep_Angle"]),
            trailing_edge_thickness_mm=float(values["Trailing_Edge_Thickness"]),
            fairing_size_mm=float(values["Fairing_Size"]),
            root_naca=normalize_naca_code(values["Root_NACA_Airfoil"]),
            mid_naca=normalize_naca_code(values["Mid_NACA_Airfoil"]),
            tip_naca=normalize_naca_code(values["Tip_NACA_Airfoil"]),
            transition_point=float(values["Transition_Point"]),
            profile_points=int(values["Profile_Points"]),
        )
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.propeller_diameter_mm <= 0.0:
            raise ValueError("Propeller_Diameter deve ser positivo.")
        if self.hub_diameter_mm <= 0.0 or self.hub_diameter_mm >= self.propeller_diameter_mm:
            raise ValueError("Hub_Diameter deve ser positivo e menor que Propeller_Diameter.")
        if self.max_chord_fraction <= 0.0:
            raise ValueError("Max_Chord_Fraction deve ser positivo.")
        if self.root_length_mm <= 0.0:
            raise ValueError("Root_Length deve ser positivo.")
        if self.ellipse_length_fraction <= 1.0:
            raise ValueError("Elen_Fraction deve ser maior que 1.")
        if self.direction not in (-1, 1):
            raise ValueError("Prop_Direction deve ser -1 ou 1.")
        if not math.isfinite(self.sweep_angle_deg_per_mm):
            raise ValueError("Sweep_Angle deve ser um valor finito.")
        if not 0.0 <= self.centerline <= 1.0:
            raise ValueError("Centerline deve estar entre 0 e 1.")
        if self.trailing_edge_thickness_mm < 0.0:
            raise ValueError("Trailing_Edge_Thickness não pode ser negativa.")
        if self.fairing_size_mm < 0.0:
            raise ValueError("Fairing_Size não pode ser negativo.")
        if not 0.0 <= self.transition_point <= 1.0:
            raise ValueError("Transition_Point deve estar entre 0 e 1.")
        if self.profile_points < 0 or self.profile_points == 1:
            raise ValueError("Profile_Points deve ser 0 ou pelo menos 2.")


@dataclass(frozen=True)
class NacaParameters:
    camber_fraction: float
    camber_position_fraction: float
    thickness_fraction: float


@dataclass(frozen=True)
class SectionGeometry:
    radius_mm: float
    chord_mm: float
    geometric_angle_deg: float
    applied_angle_deg: float
    profile_points_per_surface: int
    points_mm: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class WrappedSectionGeometry:
    radius_mm: float
    chord_mm: float
    geometric_angle_deg: float
    applied_angle_deg: float
    sweep_origin_deg: float
    profile_points_per_surface: int
    points_xyz_mm: tuple[tuple[float, float, float], ...]


def normalize_naca_code(code: Any) -> str:
    text = str(code).strip()
    if text.isdigit() and len(text) <= 4:
        text = text.zfill(4)
    if len(text) != 4 or not text.isdigit():
        raise ValueError(f"Código NACA inválido: {code!r}.")
    return text


def parse_naca_4digit(code: str) -> NacaParameters:
    code = normalize_naca_code(code)
    return NacaParameters(
        camber_fraction=int(code[0]) / 100.0,
        camber_position_fraction=int(code[1]) / 10.0,
        thickness_fraction=int(code[2:]) / 100.0,
    )


def interpolate(a: float, b: float, factor: float) -> float:
    return a + (b - a) * factor


def ellipse_diameter(major_axis: float, minor_axis: float, angle_deg: float) -> float:
    """Return the diameter of an ellipse cut by a line at ``angle_deg``.

    This is the upstream SCAD ellipse_d() helper. The blade planform supplies
    the major axis and Root_Length supplies the axial minor-axis constraint.
    Using an ellipse instead of simply clipping the chord avoids a visible
    corner near the hub.
    """
    a = 0.5 * major_axis
    b = 0.5 * minor_axis
    angle = math.radians(angle_deg)
    denominator = math.hypot(b * math.cos(angle), a * math.sin(angle))
    if denominator == 0.0:
        raise ValueError("Elipse de corda degenerada.")
    return 2.0 * a * b / denominator


def geometric_angle_deg(config: BladeConfig, radius_mm: float) -> float:
    """Return the constant-pitch blade angle at an absolute radius.

    The magnitude follows atan(pitch / (2*pi*r)). Prop_Direction controls the
    sign so the same pitch magnitude can generate clockwise or
    counter-clockwise propellers.
    """
    return -config.direction * math.degrees(
        math.atan(config.effective_pitch_mm / (2.0 * math.pi * radius_mm))
    )


def sweep_origin_angle_deg(config: BladeConfig, radius_mm: float) -> float:
    """Ângulo azimutal da origem da seção na convenção usada pelo add-in.

    O SCAD calcula internamente::

        sweeprot = radius * Sweep_Angle * sign(Prop_Direction)

    Entretanto, após orientar a pá do SCAD como hélice e alinhar sua direção
    radial de referência com o +Y usado pelo add-in, o ângulo azimutal
    correspondente no Fusion possui sinal oposto. A sobreposição direta dos
    dois sólidos confirmou essa conversão.

    Portanto, na convenção do Fusion::

        theta_sweep = -radius * Sweep_Angle * sign(Prop_Direction)
    """
    if radius_mm <= 0.0:
        raise ValueError("O raio deve ser positivo para calcular Sweep_Angle.")
    direction_sign = 1.0 if config.direction > 0 else -1.0
    return -radius_mm * config.sweep_angle_deg_per_mm * direction_sign


def chord_at_radius(config: BladeConfig, radius_mm: float) -> float:
    """Calculate the ellipse-constrained airfoil chord at ``radius_mm``.

    ``z`` is measured from the hub radius, while the pitch angle uses the
    absolute radius from the propeller axis. This distinction is easy to lose
    during refactoring and materially changes the geometry.
    """
    z = radius_mm - config.root_radius_mm
    length = config.blade_length_mm
    ellipse_semimajor = config.ellipse_length_fraction * length
    max_chord_length = 2.0 * config.max_chord_fraction * length
    hub_height_constraint = min(max_chord_length, config.root_length_mm)

    sqrt_argument = 1.0 - (z * z) / (ellipse_semimajor * ellipse_semimajor)
    if sqrt_argument < -1e-12:
        raise ValueError(f"Raio {radius_mm:g} mm fora da elipse de corda.")
    ellipse_width = max_chord_length * math.sqrt(max(0.0, sqrt_argument))
    return ellipse_diameter(
        ellipse_width,
        hub_height_constraint,
        geometric_angle_deg(config, radius_mm),
    )


def base_naca_at_radius(config: BladeConfig, radius_mm: float) -> NacaParameters:
    """Interpolate camber, camber position and thickness along the blade.

    Root -> mid uses sin(pi/2 * fraction), ending with zero slope.
    Mid -> tip uses 1-cos(pi/2 * fraction), starting with zero slope.
    These easing functions reproduce the smooth SCAD transitions.
    """
    root = parse_naca_4digit(config.root_naca)
    mid = parse_naca_4digit(config.mid_naca)
    tip = parse_naca_4digit(config.tip_naca)

    z = radius_mm - config.root_radius_mm
    length = config.blade_length_mm
    z_transition = length * config.transition_point

    if z_transition > 0.0 and z <= z_transition + 1e-12:
        factor = math.sin((math.pi / 2.0) * (z / z_transition))
        return NacaParameters(
            interpolate(root.camber_fraction, mid.camber_fraction, factor),
            interpolate(root.camber_position_fraction, mid.camber_position_fraction, factor),
            interpolate(root.thickness_fraction, mid.thickness_fraction, factor),
        )

    remaining_length = length - z_transition
    if remaining_length <= 0.0:
        return mid

    distance_after_transition = max(0.0, z - z_transition)
    factor = 1.0 - math.cos(
        (math.pi / 2.0) * (distance_after_transition / remaining_length)
    )
    factor = min(1.0, max(0.0, factor))
    return NacaParameters(
        interpolate(mid.camber_fraction, tip.camber_fraction, factor),
        interpolate(mid.camber_position_fraction, tip.camber_position_fraction, factor),
        interpolate(mid.thickness_fraction, tip.thickness_fraction, factor),
    )


def fairing_addition_fraction(config: BladeConfig, radius_mm: float) -> float:
    """Return the extra root-thickness fraction used for the hub fairing.

    Fairing_Size is a physical millimetre increase at the root. It is converted
    to an airfoil thickness fraction using the local root chord and eased to
    zero over the same radial distance.
    """
    if config.fairing_size_mm <= 0.0:
        return 0.0
    z = radius_mm - config.root_radius_mm
    root_chord = chord_at_radius(config, config.root_radius_mm)
    root_fraction = config.fairing_size_mm / root_chord
    decay_position = min(1.0, max(0.0, z / config.fairing_size_mm))
    return root_fraction * (1.0 - math.sin((math.pi / 2.0) * decay_position))


def final_naca_at_radius(config: BladeConfig, radius_mm: float) -> NacaParameters:
    base = base_naca_at_radius(config, radius_mm)
    return NacaParameters(
        base.camber_fraction,
        base.camber_position_fraction,
        base.thickness_fraction + fairing_addition_fraction(config, radius_mm),
    )


def naca_camber(x: float, m: float, p: float) -> float:
    if m == 0.0:
        return 0.0
    if not 0.0 < p < 1.0:
        raise ValueError("Perfil cambado exige posição da cambagem entre 0 e 1.")
    if x < p:
        return m * (2.0 * p * x - x * x) / (p * p)
    return m * (1.0 - 2.0 * p + 2.0 * p * x - x * x) / ((1.0 - p) ** 2)


def naca_gradient(x: float, m: float, p: float) -> float:
    if m == 0.0:
        return 0.0
    if not 0.0 < p < 1.0:
        raise ValueError("Perfil cambado exige posição da cambagem entre 0 e 1.")
    denominator = p * p if x < p else (1.0 - p) ** 2
    return 2.0 * m * (p - x) / denominator


def naca_thickness(x: float, thickness_fraction: float) -> float:
    return 5.0 * thickness_fraction * (
        0.2969 * math.sqrt(max(0.0, x))
        - 0.1260 * x
        - 0.3516 * x**2
        + 0.2843 * x**3
        - 0.1036 * x**4
    )


def normalized_surface_point(
    x_parameter: float,
    params: NacaParameters,
    trailing_edge_gap_fraction: float,
    upper: bool,
) -> tuple[float, float]:
    x = 0.5 * (1.0 - math.cos(math.pi * x_parameter))
    theta = math.atan(naca_gradient(x, params.camber_fraction, params.camber_position_fraction))
    yc = naca_camber(x, params.camber_fraction, params.camber_position_fraction)
    yt = naca_thickness(x, params.thickness_fraction)

    if upper:
        return (
            x - yt * math.sin(theta),
            yc + yt * math.cos(theta) + x * trailing_edge_gap_fraction / 2.0,
        )
    return (
        x + yt * math.sin(theta),
        yc - yt * math.cos(theta) - x * trailing_edge_gap_fraction / 2.0,
    )



def airfoil_ring_profile_points(
    naca_code: str,
    chord_mm: float,
    reference_radius_mm: float,
    axial_offset_mm: float,
    trailing_edge_thickness_mm: float,
    points_per_surface: int = 20,
) -> tuple[tuple[float, float], ...]:
    """Return the radial/axial contour used by the upstream airfoil ring.

    The original OpenSCAD demonstration performs:

        translate([radius, 0])
        rotate(-90 deg)
        polygon(NACA_profile(
            20, M, P, T,
            chordlen=chord,
            origin=1,
            dir=1,
            te_thick=0.4
        ))

    ``NACA_profile`` is first expressed with its origin at the trailing edge.
    After the -90 degree rotation:

    * airfoil thickness becomes radial displacement about ``reference_radius``;
    * the trailing edge lies at ``axial_offset_mm``;
    * the rounded leading edge lies approximately one chord in +Z.

    The finite trailing-edge thickness is physical millimetres, matching the
    upstream helper rather than being a percentage of chord.
    """
    code = normalize_naca_code(naca_code)
    params = parse_naca_4digit(code)

    if chord_mm <= 0.0:
        raise ValueError("Airfoil_Ring_Chord deve ser positivo.")
    if reference_radius_mm <= 0.0:
        raise ValueError("Airfoil_Ring_Diameter deve ser positivo.")
    if trailing_edge_thickness_mm < 0.0:
        raise ValueError(
            "Airfoil_Ring_TE_Thickness não pode ser negativa."
        )
    if points_per_surface < 2:
        raise ValueError(
            "Airfoil_Ring_Profile_Points deve ser pelo menos 2."
        )

    trailing_edge_gap_fraction = (
        trailing_edge_thickness_mm / chord_mm
    )
    samples = [
        index / points_per_surface
        for index in range(points_per_surface + 1)
    ]

    upper = [
        normalized_surface_point(
            sample,
            params,
            trailing_edge_gap_fraction,
            True,
        )
        for sample in samples
    ]
    lower = [
        normalized_surface_point(
            sample,
            params,
            trailing_edge_gap_fraction,
            False,
        )
        for sample in samples
    ]

    # This ordering matches NACA_profile(..., origin=1, dir=1):
    # upper trailing edge -> leading edge -> lower trailing edge.
    normalized_contour = upper[::-1] + lower[1:]

    result: list[tuple[float, float]] = []
    for x_normalized, y_normalized in normalized_contour:
        radial_mm = reference_radius_mm + chord_mm * y_normalized
        axial_mm = (
            axial_offset_mm
            + chord_mm * (1.0 - x_normalized)
        )
        result.append((radial_mm, axial_mm))

    return tuple(result)

def validate_radii(config: BladeConfig, radii: Sequence[float]) -> list[float]:
    result = sorted({float(radius) for radius in radii})
    if not result:
        raise ValueError("Informe pelo menos um raio.")
    for radius in result:
        if radius < config.root_radius_mm - 1e-9:
            raise ValueError(
                f"Raio {radius:g} mm menor que a raiz ({config.root_radius_mm:g} mm)."
            )
        if radius > config.tip_radius_mm + 1e-9:
            raise ValueError(
                f"Raio {radius:g} mm maior que a ponta ({config.tip_radius_mm:g} mm)."
            )
    return result



def _sorted_unique_radii(
    values: Sequence[float],
    tolerance_mm: float = 1e-9,
) -> list[float]:
    ordered = sorted(float(value) for value in values)
    unique: list[float] = []
    for value in ordered:
        if not unique or abs(value - unique[-1]) > tolerance_mm:
            unique.append(value)
    return unique


def _radii_with_special_sections(
    config: BladeConfig,
    base_radii: Sequence[float],
) -> list[float]:
    """Inclui raiz, transição NACA e ponta exatamente, sem duplicatas."""
    values = list(base_radii)
    values.append(config.root_radius_mm)
    values.append(config.tip_radius_mm)

    transition_radius_mm = (
        config.root_radius_mm
        + config.blade_length_mm * config.transition_point
    )
    if (
        transition_radius_mm > config.root_radius_mm + 1e-9
        and transition_radius_mm < config.tip_radius_mm - 1e-9
    ):
        values.append(transition_radius_mm)

    return validate_radii(config, _sorted_unique_radii(values))


def section_radii_from_spacing(
    config: BladeConfig,
    spacing_mm: float,
    maximum_sections: int = 1000,
) -> list[float]:
    """Gera seções a partir da raiz com espaçamento radial aproximadamente constante.

    A ponta e o raio exato da transição são acrescentados mesmo quando não
    coincidem com a malha regular. Por isso o último intervalo pode ser menor
    e a quantidade final pode exceder em uma unidade a estimativa simples.
    """
    spacing_mm = float(spacing_mm)
    if not math.isfinite(spacing_mm) or spacing_mm <= 0.0:
        raise ValueError('O espaçamento radial deve ser positivo e finito.')

    length_mm = config.blade_length_mm
    estimated_regular_count = int(math.floor(length_mm / spacing_mm)) + 1
    if estimated_regular_count + 2 > maximum_sections:
        raise ValueError(
            'O espaçamento solicitado criaria seções demais. '
            f'Use pelo menos {length_mm / max(1, maximum_sections - 2):.6g} mm.'
        )

    values = [config.root_radius_mm]
    index = 1
    while True:
        radius_mm = config.root_radius_mm + index * spacing_mm
        if radius_mm >= config.tip_radius_mm - 1e-9:
            break
        values.append(radius_mm)
        index += 1

    result = _radii_with_special_sections(config, values)
    if len(result) > maximum_sections:
        raise ValueError(
            f'A distribuição resultou em {len(result)} seções; '
            f'o limite é {maximum_sections}.'
        )
    return result


def section_radii_from_slices(
    config: BladeConfig,
    slices: int,
    maximum_sections: int = 1000,
) -> list[float]:
    """Divide o comprimento radial em ``slices`` intervalos iguais.

    A malha-base contém ``slices + 1`` seções. O raio exato da transição NACA
    é incluído adicionalmente quando não coincide com uma dessas seções.
    """
    slices = int(slices)
    if slices < 1:
        raise ValueError('Slices deve ser pelo menos 1.')
    if slices + 2 > maximum_sections:
        raise ValueError(
            f'Slices={slices} pode exceder o limite de {maximum_sections} seções.'
        )

    step_mm = config.blade_length_mm / slices
    values = [
        config.root_radius_mm + step_mm * index
        for index in range(slices + 1)
    ]
    result = _radii_with_special_sections(config, values)
    if len(result) > maximum_sections:
        raise ValueError(
            f'A distribuição resultou em {len(result)} seções; '
            f'o limite é {maximum_sections}.'
        )
    return result

def _resolved_profile_points(
    config: BladeConfig,
    profile_points_override: int | None,
) -> int:
    n = config.profile_points if profile_points_override is None else int(profile_points_override)
    if n == 0:
        n = max(2, round(2.0 * config.blade_length_mm * config.max_chord_fraction))
    if n < 2:
        raise ValueError("Profile_Points deve ser 0 ou pelo menos 2.")
    return n


def section_geometry(
    config: BladeConfig,
    radius_mm: float,
    apply_geometric_angle: bool = True,
    profile_points_override: int | None = None,
) -> SectionGeometry:
    """Build one dimensional planar airfoil section.

    The returned point order follows the SCAD polygon order around the airfoil
    and includes the modified physical trailing-edge thickness.
    """
    """Gera a seção plana física no plano tangente XZ.

    X é a direção tangencial/corda e Z é a direção axial da hélice. O ponto
    médio do bordo de fuga obedece a Centerline, e Prop_Direction segue a
    convenção matemática do gerador SCAD.
    """
    chord_mm = chord_at_radius(config, radius_mm)
    angle_deg = geometric_angle_deg(config, radius_mm)
    params = final_naca_at_radius(config, radius_mm)
    n = _resolved_profile_points(config, profile_points_override)

    trailing_edge_gap_fraction = config.trailing_edge_thickness_mm / chord_mm
    samples = [i / n for i in range(n + 1)]

    upper = [
        normalized_surface_point(s, params, trailing_edge_gap_fraction, True)
        for s in samples
    ]
    lower = [
        normalized_surface_point(s, params, trailing_edge_gap_fraction, False)
        for s in samples
    ]
    normalized_contour = upper[::-1] + lower[1:]

    # O ângulo retornado por geometric_angle_deg segue a convenção matemática
    # do SCAD. Na vista frontal padrão do Fusion (X para a direita e Z para
    # cima), o sinal visual precisa ser invertido.
    applied_angle_deg = -angle_deg if apply_geometric_angle else 0.0
    angle = math.radians(applied_angle_deg)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    axial_offset_mm = (1.0 - config.centerline) * config.root_length_mm

    points: list[tuple[float, float]] = []
    for x_normalized, y_normalized in normalized_contour:
        x_mm = config.direction * chord_mm * (config.centerline - x_normalized)
        z_mm = chord_mm * y_normalized

        x_rotated = cos_angle * x_mm - sin_angle * z_mm
        z_rotated = sin_angle * x_mm + cos_angle * z_mm + axial_offset_mm
        points.append((x_rotated, z_rotated))

    return SectionGeometry(
        radius_mm=radius_mm,
        chord_mm=chord_mm,
        geometric_angle_deg=angle_deg,
        applied_angle_deg=applied_angle_deg,
        profile_points_per_surface=n,
        points_mm=tuple(points),
    )


def wrapped_section_geometry(
    config: BladeConfig,
    radius_mm: float,
    apply_geometric_angle: bool = True,
    profile_points_override: int | None = None,
) -> WrappedSectionGeometry:
    """Map a planar section onto its cylindrical surface around the Z axis.

    Chordwise displacement becomes azimuth, section height remains axial Z and
    Sweep_Angle rotates the section origin around the shaft. The cylindrical
    radius must remain exactly ``radius_mm`` for every returned point.
    """
    """Enrola a seção plana sobre um cilindro coaxial ao eixo Z.

    Convenção desta primeira implementação no Fusion:
      * eixo da hélice: Z;
      * direção radial de referência da primeira pá: +Y;
      * X plano é tratado como comprimento de arco tangencial;
      * em X=0 e Sweep_Angle=0, o ponto fica em (0, +R, Z).

    A transformação é:
        theta = X_plano/R + theta_sweep
        X_3D = R*sin(theta)
        Y_3D = R*cos(theta)
        Z_3D = Z_plano

    Assim, próximo da direção +Y, um deslocamento tangencial positivo no perfil
    plano continua aparecendo no sentido +X global.
    """
    if radius_mm <= 0.0:
        raise ValueError("O raio deve ser positivo para enrolar a seção.")

    flat = section_geometry(
        config,
        radius_mm,
        apply_geometric_angle=apply_geometric_angle,
        profile_points_override=profile_points_override,
    )

    sweep_origin_deg = sweep_origin_angle_deg(config, radius_mm)
    sweep_origin_rad = math.radians(sweep_origin_deg)

    points_xyz: list[tuple[float, float, float]] = []
    for tangential_mm, axial_mm in flat.points_mm:
        theta = tangential_mm / radius_mm + sweep_origin_rad
        x_mm = radius_mm * math.sin(theta)
        y_mm = radius_mm * math.cos(theta)
        z_mm = axial_mm
        points_xyz.append((x_mm, y_mm, z_mm))

    # Verificação interna: todos os pontos da spline devem estar sobre o
    # cilindro de raio solicitado. A reta que fecha o BF será criada depois e
    # pode atravessar ligeiramente o interior do cilindro.
    max_radius_error = max(
        abs(math.hypot(x_mm, y_mm) - radius_mm)
        for x_mm, y_mm, _ in points_xyz
    )
    if max_radius_error > 1e-9:
        raise RuntimeError(
            "Falha interna ao enrolar a seção: os pontos não permaneceram "
            f"no cilindro R={radius_mm:g} mm."
        )

    return WrappedSectionGeometry(
        radius_mm=radius_mm,
        chord_mm=flat.chord_mm,
        geometric_angle_deg=flat.geometric_angle_deg,
        applied_angle_deg=flat.applied_angle_deg,
        sweep_origin_deg=sweep_origin_deg,
        profile_points_per_surface=flat.profile_points_per_surface,
        points_xyz_mm=tuple(points_xyz),
    )
